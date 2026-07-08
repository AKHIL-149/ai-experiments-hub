"""
Agent Auction System Service

Manages auctions for task allocation and resource distribution using various
auction mechanisms (first-price, second-price, Dutch, English, Vickrey).
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict
import random


class AuctionType:
    """Auction types"""
    FIRST_PRICE = "first_price"
    SECOND_PRICE = "second_price"
    ENGLISH = "english"
    DUTCH = "dutch"
    VICKREY = "vickrey"
    COMBINATORIAL = "combinatorial"


class AuctionStatus:
    """Auction statuses"""
    OPEN = "open"
    ACTIVE = "active"
    CLOSED = "closed"
    AWARDED = "awarded"
    CANCELLED = "cancelled"


class BidStatus:
    """Bid statuses"""
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    OUTBID = "outbid"
    WITHDRAWN = "withdrawn"


class AgentAuction:
    """
    Agent Auction System

    Manages task and resource auctions using various mechanisms.
    Enables efficient allocation through competitive bidding.
    """

    # In-memory storage
    _auctions = {}
    _auction_counter = 0

    _bids = defaultdict(list)  # auction_id -> [bids]
    _agent_bids = defaultdict(list)  # agent_id -> [bid_ids]
    _auction_history = []

    @staticmethod
    def create_auction(
        session,
        auction_type: str,
        auctioneer_agent_id: int,
        item_type: str,
        item_description: str,
        reserve_price: Optional[float] = None,
        starting_price: Optional[float] = None,
        duration_minutes: int = 60,
        item_metadata: Optional[dict] = None,
        auction_rules: Optional[dict] = None
    ) -> dict:
        """
        Create a new auction.

        Args:
            session: Database session
            auction_type: Type of auction mechanism
            auctioneer_agent_id: Agent hosting the auction
            item_type: Type of item being auctioned
            item_description: Description of item
            reserve_price: Minimum acceptable price
            starting_price: Starting bid price
            duration_minutes: Auction duration
            item_metadata: Item metadata
            auction_rules: Custom auction rules

        Returns:
            Auction record
        """
        AgentAuction._auction_counter += 1
        auction_id = f"auction_{AgentAuction._auction_counter}"

        start_time = datetime.utcnow()
        end_time = start_time + timedelta(minutes=duration_minutes)

        auction = {
            "id": auction_id,
            "auction_type": auction_type,
            "auctioneer_agent_id": auctioneer_agent_id,
            "item_type": item_type,
            "item_description": item_description,
            "reserve_price": reserve_price,
            "starting_price": starting_price or 0.0,
            "current_price": starting_price or 0.0,
            "winning_bid": None,
            "winning_agent_id": None,
            "status": AuctionStatus.OPEN,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_minutes": duration_minutes,
            "item_metadata": item_metadata or {},
            "auction_rules": auction_rules or {},
            "created_at": datetime.utcnow().isoformat(),
            "bid_count": 0,
            "participant_count": 0,
            "highest_bid": None,
            "second_highest_bid": None
        }

        AgentAuction._auctions[auction_id] = auction

        return auction

    @staticmethod
    def place_bid(
        session,
        auction_id: str,
        bidder_agent_id: int,
        bid_amount: float,
        max_bid: Optional[float] = None,
        bid_metadata: Optional[dict] = None
    ) -> dict:
        """
        Place a bid on an auction.

        Args:
            session: Database session
            auction_id: Auction ID
            bidder_agent_id: Bidding agent ID
            bid_amount: Bid amount
            max_bid: Maximum bid (for proxy bidding)
            bid_metadata: Bid metadata

        Returns:
            Bid record
        """
        if auction_id not in AgentAuction._auctions:
            raise ValueError(f"Auction {auction_id} not found")

        auction = AgentAuction._auctions[auction_id]

        if auction["status"] not in [AuctionStatus.OPEN, AuctionStatus.ACTIVE]:
            raise ValueError(f"Auction is {auction['status']}, cannot place bid")

        # Check if auction has ended
        if datetime.fromisoformat(auction["end_time"]) < datetime.utcnow():
            auction["status"] = AuctionStatus.CLOSED
            raise ValueError("Auction has ended")

        # Validate bid amount
        if bid_amount < auction["starting_price"]:
            raise ValueError(f"Bid must be at least {auction['starting_price']}")

        if auction["current_price"] and bid_amount <= auction["current_price"]:
            raise ValueError(f"Bid must be higher than current price {auction['current_price']}")

        # Create bid
        bid_id = f"bid_{len(AgentAuction._bids[auction_id]) + 1}"
        bid = {
            "id": bid_id,
            "auction_id": auction_id,
            "bidder_agent_id": bidder_agent_id,
            "bid_amount": bid_amount,
            "max_bid": max_bid or bid_amount,
            "status": BidStatus.PENDING,
            "placed_at": datetime.utcnow().isoformat(),
            "metadata": bid_metadata or {}
        }

        AgentAuction._bids[auction_id].append(bid)
        AgentAuction._agent_bids[bidder_agent_id].append(bid_id)

        # Update auction
        auction["bid_count"] += 1
        if auction["status"] == AuctionStatus.OPEN:
            auction["status"] = AuctionStatus.ACTIVE

        # Track unique participants
        bidder_ids = {b["bidder_agent_id"] for b in AgentAuction._bids[auction_id]}
        auction["participant_count"] = len(bidder_ids)

        # Update current price and highest bids
        AgentAuction._update_auction_state(auction_id)

        return bid

    @staticmethod
    def get_auction(
        session,
        auction_id: str
    ) -> dict:
        """
        Get auction details.

        Args:
            session: Database session
            auction_id: Auction ID

        Returns:
            Auction with bids
        """
        if auction_id not in AgentAuction._auctions:
            raise ValueError(f"Auction {auction_id} not found")

        auction = AgentAuction._auctions[auction_id]
        bids = AgentAuction._bids.get(auction_id, [])

        # Check if auction should be closed
        if auction["status"] == AuctionStatus.ACTIVE:
            if datetime.fromisoformat(auction["end_time"]) < datetime.utcnow():
                AgentAuction._close_auction(auction_id)

        return {
            **auction,
            "bids": bids,
            "time_remaining": AgentAuction._calculate_time_remaining(auction)
        }

    @staticmethod
    def close_auction(
        session,
        auction_id: str,
        force_close: bool = False
    ) -> dict:
        """
        Close an auction and determine winner.

        Args:
            session: Database session
            auction_id: Auction ID
            force_close: Force close before end time

        Returns:
            Auction result
        """
        if auction_id not in AgentAuction._auctions:
            raise ValueError(f"Auction {auction_id} not found")

        auction = AgentAuction._auctions[auction_id]

        if auction["status"] == AuctionStatus.CLOSED:
            raise ValueError("Auction already closed")

        if not force_close and datetime.fromisoformat(auction["end_time"]) > datetime.utcnow():
            raise ValueError("Auction has not ended yet")

        return AgentAuction._close_auction(auction_id)

    @staticmethod
    def cancel_auction(
        session,
        auction_id: str,
        reason: str
    ) -> dict:
        """
        Cancel an auction.

        Args:
            session: Database session
            auction_id: Auction ID
            reason: Cancellation reason

        Returns:
            Cancellation result
        """
        if auction_id not in AgentAuction._auctions:
            raise ValueError(f"Auction {auction_id} not found")

        auction = AgentAuction._auctions[auction_id]

        if auction["status"] in [AuctionStatus.CLOSED, AuctionStatus.AWARDED]:
            raise ValueError(f"Cannot cancel auction in {auction['status']} status")

        auction["status"] = AuctionStatus.CANCELLED
        auction["metadata"] = {
            **auction.get("metadata", {}),
            "cancellation_reason": reason,
            "cancelled_at": datetime.utcnow().isoformat()
        }

        # Mark all bids as rejected
        for bid in AgentAuction._bids.get(auction_id, []):
            if bid["status"] == BidStatus.PENDING:
                bid["status"] = BidStatus.REJECTED

        return {
            "auction_id": auction_id,
            "cancelled_at": datetime.utcnow().isoformat(),
            "reason": reason,
            "refunded_bids": len(AgentAuction._bids.get(auction_id, []))
        }

    @staticmethod
    def withdraw_bid(
        session,
        auction_id: str,
        bidder_agent_id: int
    ) -> dict:
        """
        Withdraw a bid from an auction.

        Args:
            session: Database session
            auction_id: Auction ID
            bidder_agent_id: Bidding agent ID

        Returns:
            Withdrawal result
        """
        if auction_id not in AgentAuction._auctions:
            raise ValueError(f"Auction {auction_id} not found")

        auction = AgentAuction._auctions[auction_id]
        bids = AgentAuction._bids.get(auction_id, [])

        # Find agent's pending bid
        agent_bids = [b for b in bids if b["bidder_agent_id"] == bidder_agent_id and b["status"] == BidStatus.PENDING]

        if not agent_bids:
            raise ValueError("No pending bid found for agent")

        # Withdraw the most recent bid
        bid = agent_bids[-1]
        bid["status"] = BidStatus.WITHDRAWN
        bid["withdrawn_at"] = datetime.utcnow().isoformat()

        # Update auction state
        AgentAuction._update_auction_state(auction_id)

        return {
            "bid_id": bid["id"],
            "withdrawn_at": bid["withdrawn_at"],
            "refund_amount": bid["bid_amount"]
        }

    @staticmethod
    def list_auctions(
        session,
        status: Optional[str] = None,
        item_type: Optional[str] = None,
        auctioneer_agent_id: Optional[int] = None
    ) -> dict:
        """
        List all auctions with filtering.

        Args:
            session: Database session
            status: Filter by status
            item_type: Filter by item type
            auctioneer_agent_id: Filter by auctioneer

        Returns:
            Filtered auction list
        """
        auctions = list(AgentAuction._auctions.values())

        if status:
            auctions = [a for a in auctions if a["status"] == status]

        if item_type:
            auctions = [a for a in auctions if a["item_type"] == item_type]

        if auctioneer_agent_id is not None:
            auctions = [a for a in auctions if a["auctioneer_agent_id"] == auctioneer_agent_id]

        # Sort by creation time
        auctions.sort(key=lambda a: a["created_at"], reverse=True)

        return {
            "total": len(auctions),
            "auctions": auctions
        }

    @staticmethod
    def get_agent_bids(
        session,
        agent_id: int,
        status: Optional[str] = None
    ) -> dict:
        """
        Get all bids by an agent.

        Args:
            session: Database session
            agent_id: Agent ID
            status: Filter by bid status

        Returns:
            Agent's bids
        """
        all_bids = []
        for auction_id, bids in AgentAuction._bids.items():
            agent_bids = [b for b in bids if b["bidder_agent_id"] == agent_id]
            all_bids.extend(agent_bids)

        if status:
            all_bids = [b for b in all_bids if b["status"] == status]

        # Calculate statistics
        total_bid_amount = sum(b["bid_amount"] for b in all_bids)
        won_bids = [b for b in all_bids if b["status"] == BidStatus.ACCEPTED]
        win_rate = len(won_bids) / len(all_bids) if all_bids else 0.0

        return {
            "agent_id": agent_id,
            "total_bids": len(all_bids),
            "total_bid_amount": total_bid_amount,
            "won_bids": len(won_bids),
            "win_rate": win_rate,
            "bids": all_bids
        }

    @staticmethod
    def get_auction_statistics(session) -> dict:
        """
        Get auction system statistics.

        Args:
            session: Database session

        Returns:
            System statistics
        """
        total_auctions = len(AgentAuction._auctions)

        # Count by status
        by_status = defaultdict(int)
        for auction in AgentAuction._auctions.values():
            by_status[auction["status"]] += 1

        # Count by type
        by_type = defaultdict(int)
        for auction in AgentAuction._auctions.values():
            by_type[auction["auction_type"]] += 1

        # Bid statistics
        total_bids = sum(len(bids) for bids in AgentAuction._bids.values())
        total_bid_value = sum(
            sum(b["bid_amount"] for b in bids)
            for bids in AgentAuction._bids.values()
        )

        # Awarded auctions
        awarded = [a for a in AgentAuction._auctions.values() if a["status"] == AuctionStatus.AWARDED]
        avg_winning_price = (
            sum(a["winning_bid"]["bid_amount"] for a in awarded if a["winning_bid"])
            / len(awarded) if awarded else 0.0
        )

        return {
            "total_auctions": total_auctions,
            "auctions_by_status": dict(by_status),
            "auctions_by_type": dict(by_type),
            "total_bids": total_bids,
            "total_bid_value": total_bid_value,
            "awarded_auctions": len(awarded),
            "average_winning_price": avg_winning_price
        }

    # Helper methods

    @staticmethod
    def _update_auction_state(auction_id: str):
        """Update auction current price and highest bids"""
        auction = AgentAuction._auctions[auction_id]
        bids = AgentAuction._bids.get(auction_id, [])

        # Get active bids
        active_bids = [b for b in bids if b["status"] == BidStatus.PENDING]

        if not active_bids:
            return

        # Sort by bid amount
        sorted_bids = sorted(active_bids, key=lambda b: b["bid_amount"], reverse=True)

        # Update highest and second highest
        auction["highest_bid"] = sorted_bids[0] if sorted_bids else None
        auction["second_highest_bid"] = sorted_bids[1] if len(sorted_bids) > 1 else None

        # Update current price based on auction type
        if auction["auction_type"] == AuctionType.ENGLISH:
            # Current price is highest bid
            auction["current_price"] = sorted_bids[0]["bid_amount"]
        elif auction["auction_type"] == AuctionType.DUTCH:
            # Price decreases over time
            elapsed = (datetime.utcnow() - datetime.fromisoformat(auction["start_time"])).total_seconds()
            total_duration = auction["duration_minutes"] * 60
            price_reduction = (auction["starting_price"] - (auction["reserve_price"] or 0)) * (elapsed / total_duration)
            auction["current_price"] = max(auction["starting_price"] - price_reduction, auction["reserve_price"] or 0)

        # Mark outbid bids
        if len(sorted_bids) > 1:
            for bid in sorted_bids[1:]:
                bid["status"] = BidStatus.OUTBID

    @staticmethod
    def _close_auction(auction_id: str) -> dict:
        """Close auction and determine winner"""
        auction = AgentAuction._auctions[auction_id]
        bids = AgentAuction._bids.get(auction_id, [])

        active_bids = [b for b in bids if b["status"] == BidStatus.PENDING]

        if not active_bids:
            auction["status"] = AuctionStatus.CLOSED
            return {
                "auction_id": auction_id,
                "winner": None,
                "winning_price": None,
                "message": "No valid bids"
            }

        # Sort bids
        sorted_bids = sorted(active_bids, key=lambda b: b["bid_amount"], reverse=True)
        highest_bid = sorted_bids[0]

        # Check reserve price
        if auction["reserve_price"] and highest_bid["bid_amount"] < auction["reserve_price"]:
            auction["status"] = AuctionStatus.CLOSED
            for bid in active_bids:
                bid["status"] = BidStatus.REJECTED
            return {
                "auction_id": auction_id,
                "winner": None,
                "winning_price": None,
                "message": "Reserve price not met"
            }

        # Determine winning price based on auction type
        winning_price = highest_bid["bid_amount"]

        if auction["auction_type"] == AuctionType.SECOND_PRICE or auction["auction_type"] == AuctionType.VICKREY:
            # Winner pays second-highest price
            if len(sorted_bids) > 1:
                winning_price = sorted_bids[1]["bid_amount"]
            else:
                winning_price = auction["reserve_price"] or auction["starting_price"]

        # Award auction
        highest_bid["status"] = BidStatus.ACCEPTED
        auction["winning_bid"] = highest_bid
        auction["winning_agent_id"] = highest_bid["bidder_agent_id"]
        auction["status"] = AuctionStatus.AWARDED
        auction["awarded_at"] = datetime.utcnow().isoformat()

        # Reject other bids
        for bid in sorted_bids[1:]:
            bid["status"] = BidStatus.REJECTED

        # Add to history
        AgentAuction._auction_history.append({
            "auction_id": auction_id,
            "winner_agent_id": highest_bid["bidder_agent_id"],
            "winning_price": winning_price,
            "total_bids": len(bids),
            "awarded_at": auction["awarded_at"]
        })

        return {
            "auction_id": auction_id,
            "winner_agent_id": highest_bid["bidder_agent_id"],
            "winning_price": winning_price,
            "auction_type": auction["auction_type"],
            "total_bids": len(bids),
            "awarded_at": auction["awarded_at"]
        }

    @staticmethod
    def _calculate_time_remaining(auction: dict) -> dict:
        """Calculate time remaining in auction"""
        end_time = datetime.fromisoformat(auction["end_time"])
        now = datetime.utcnow()

        if now >= end_time:
            return {
                "seconds": 0,
                "minutes": 0,
                "expired": True
            }

        delta = end_time - now
        return {
            "seconds": int(delta.total_seconds()),
            "minutes": int(delta.total_seconds() / 60),
            "expired": False
        }
