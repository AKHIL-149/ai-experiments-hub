"""
Agent Auction System API

REST API endpoints for managing auctions and bids.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.agent_auction import (
    AgentAuction,
    AuctionType,
    AuctionStatus,
    BidStatus
)


router = APIRouter()


# Request/Response Models
class CreateAuctionRequest(BaseModel):
    auction_type: str = Field(..., description="Auction type")
    item_type: str = Field(..., description="Item type")
    item_description: str = Field(..., description="Item description")
    reserve_price: Optional[float] = Field(None, description="Reserve price")
    starting_price: Optional[float] = Field(None, description="Starting price")
    duration_minutes: int = Field(60, description="Auction duration in minutes")
    item_metadata: Optional[dict] = Field(None, description="Item metadata")
    auction_rules: Optional[dict] = Field(None, description="Auction rules")


class PlaceBidRequest(BaseModel):
    bid_amount: float = Field(..., description="Bid amount")
    max_bid: Optional[float] = Field(None, description="Maximum bid for proxy bidding")
    bid_metadata: Optional[dict] = Field(None, description="Bid metadata")


class CloseAuctionRequest(BaseModel):
    force_close: bool = Field(False, description="Force close before end time")


class CancelAuctionRequest(BaseModel):
    reason: str = Field(..., description="Cancellation reason")


@router.post("/auctions")
def create_auction(
    auctioneer_agent_id: int,
    request: CreateAuctionRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a new auction.

    Auctioneer creates an auction for a task or resource.
    Auction starts immediately and runs for specified duration.
    """
    try:
        auction = AgentAuction.create_auction(
            session=session,
            auction_type=request.auction_type,
            auctioneer_agent_id=auctioneer_agent_id,
            item_type=request.item_type,
            item_description=request.item_description,
            reserve_price=request.reserve_price,
            starting_price=request.starting_price,
            duration_minutes=request.duration_minutes,
            item_metadata=request.item_metadata,
            auction_rules=request.auction_rules
        )

        return {
            "success": True,
            "auction": auction,
            "message": f"Auction created: {request.item_description}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auctions/{auction_id}/bids")
def place_bid(
    auction_id: str,
    bidder_agent_id: int,
    request: PlaceBidRequest,
    session: Session = Depends(get_db_session)
):
    """
    Place a bid on an auction.

    Agent places a bid with specified amount. Bid must be higher than
    current price. Supports proxy bidding with max_bid parameter.
    """
    try:
        bid = AgentAuction.place_bid(
            session=session,
            auction_id=auction_id,
            bidder_agent_id=bidder_agent_id,
            bid_amount=request.bid_amount,
            max_bid=request.max_bid,
            bid_metadata=request.bid_metadata
        )

        return {
            "success": True,
            "bid": bid,
            "message": f"Bid placed: ${request.bid_amount}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/auctions/{auction_id}")
def get_auction(
    auction_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Get auction details.

    Returns complete auction information including all bids,
    current status, and time remaining.
    """
    try:
        auction = AgentAuction.get_auction(
            session=session,
            auction_id=auction_id
        )

        return {
            "success": True,
            "auction": auction
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auctions/{auction_id}/close")
def close_auction(
    auction_id: str,
    request: CloseAuctionRequest = CloseAuctionRequest(),
    session: Session = Depends(get_db_session)
):
    """
    Close an auction.

    Closes auction and determines winner based on auction type.
    For second-price and Vickrey auctions, winner pays second-highest price.
    """
    try:
        result = AgentAuction.close_auction(
            session=session,
            auction_id=auction_id,
            force_close=request.force_close
        )

        return {
            "success": True,
            **result,
            "message": "Auction closed"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/auctions/{auction_id}/cancel")
def cancel_auction(
    auction_id: str,
    request: CancelAuctionRequest,
    session: Session = Depends(get_db_session)
):
    """
    Cancel an auction.

    Cancels active auction and rejects all pending bids.
    Cannot cancel already closed or awarded auctions.
    """
    try:
        result = AgentAuction.cancel_auction(
            session=session,
            auction_id=auction_id,
            reason=request.reason
        )

        return {
            "success": True,
            **result,
            "message": "Auction cancelled"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/auctions/{auction_id}/bids")
def withdraw_bid(
    auction_id: str,
    bidder_agent_id: int,
    session: Session = Depends(get_db_session)
):
    """
    Withdraw a bid from an auction.

    Withdraws agent's pending bid. Cannot withdraw after auction closes.
    """
    try:
        result = AgentAuction.withdraw_bid(
            session=session,
            auction_id=auction_id,
            bidder_agent_id=bidder_agent_id
        )

        return {
            "success": True,
            **result,
            "message": "Bid withdrawn"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/auctions")
def list_auctions(
    status: Optional[str] = None,
    item_type: Optional[str] = None,
    auctioneer_agent_id: Optional[int] = None,
    session: Session = Depends(get_db_session)
):
    """
    List all auctions.

    Returns auctions with optional filtering by status, item type,
    or auctioneer. Sorted by creation time.
    """
    try:
        result = AgentAuction.list_auctions(
            session=session,
            status=status,
            item_type=item_type,
            auctioneer_agent_id=auctioneer_agent_id
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}/bids")
def get_agent_bids(
    agent_id: int,
    status: Optional[str] = None,
    session: Session = Depends(get_db_session)
):
    """
    Get all bids by an agent.

    Returns agent's bidding history with statistics including
    total bids, win rate, and bid amounts.
    """
    try:
        result = AgentAuction.get_agent_bids(
            session=session,
            agent_id=agent_id,
            status=status
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
def get_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get auction system statistics.

    Returns aggregate data including auction counts by status and type,
    total bids, bid values, and average winning prices.
    """
    try:
        stats = AgentAuction.get_auction_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/auction-types")
def list_auction_types():
    """
    List all auction types.

    Returns all available auction mechanisms.
    """
    return {
        "success": True,
        "auction_types": [
            {"type": AuctionType.FIRST_PRICE, "description": "Highest bidder wins and pays their bid"},
            {"type": AuctionType.SECOND_PRICE, "description": "Highest bidder wins but pays second-highest bid"},
            {"type": AuctionType.ENGLISH, "description": "Ascending price auction, bidders raise bids"},
            {"type": AuctionType.DUTCH, "description": "Descending price auction, first bidder wins"},
            {"type": AuctionType.VICKREY, "description": "Sealed-bid second-price auction"},
            {"type": AuctionType.COMBINATORIAL, "description": "Auction for bundles of items"}
        ]
    }


@router.get("/auction-statuses")
def list_auction_statuses():
    """
    List all auction statuses.

    Returns all possible auction lifecycle statuses.
    """
    return {
        "success": True,
        "statuses": [
            {"status": AuctionStatus.OPEN, "description": "Auction created, accepting bids"},
            {"status": AuctionStatus.ACTIVE, "description": "Auction active with bids placed"},
            {"status": AuctionStatus.CLOSED, "description": "Auction ended, determining winner"},
            {"status": AuctionStatus.AWARDED, "description": "Auction completed, winner determined"},
            {"status": AuctionStatus.CANCELLED, "description": "Auction cancelled by auctioneer"}
        ]
    }


@router.get("/bid-statuses")
def list_bid_statuses():
    """
    List all bid statuses.

    Returns all possible bid statuses.
    """
    return {
        "success": True,
        "statuses": [
            {"status": BidStatus.PENDING, "description": "Bid active, may win"},
            {"status": BidStatus.ACCEPTED, "description": "Winning bid, accepted"},
            {"status": BidStatus.REJECTED, "description": "Bid rejected or lost"},
            {"status": BidStatus.OUTBID, "description": "Outbid by higher bid"},
            {"status": BidStatus.WITHDRAWN, "description": "Bid withdrawn by bidder"}
        ]
    }
