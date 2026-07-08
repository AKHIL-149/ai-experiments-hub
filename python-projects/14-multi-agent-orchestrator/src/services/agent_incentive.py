"""
Agent Incentive Service

Manages agent rewards, contributions, and economic incentives to encourage high-quality
performance, collaboration, and system participation.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from src.models.database import Agent
from src.core.logging import logger


class ContributionType:
    """Contribution type constants"""
    TASK_COMPLETION = "task_completion"
    COLLABORATION = "collaboration"
    ENDORSEMENT_RECEIVED = "endorsement_received"
    HELP_PROVIDED = "help_provided"
    INNOVATION = "innovation"
    QUALITY_WORK = "quality_work"


class RewardType:
    """Reward type constants"""
    BASE_REWARD = "base_reward"
    PERFORMANCE_BONUS = "performance_bonus"
    QUALITY_BONUS = "quality_bonus"
    COLLABORATION_BONUS = "collaboration_bonus"
    STREAK_BONUS = "streak_bonus"
    MILESTONE_REWARD = "milestone_reward"


class RewardStatus:
    """Reward status constants"""
    PENDING = "pending"
    APPROVED = "approved"
    DISTRIBUTED = "distributed"
    REJECTED = "rejected"


class AgentIncentive:
    """Service for managing agent incentives and rewards"""

    # In-memory storage
    _agent_balances: Dict[int, float] = {}  # agent_id -> balance
    _contributions: Dict[int, List[Dict[str, Any]]] = {}  # agent_id -> contributions
    _rewards: Dict[int, List[Dict[str, Any]]] = {}  # agent_id -> rewards
    _transactions: List[Dict[str, Any]] = []
    _reward_pools: Dict[str, Dict[str, Any]] = {}  # pool_id -> pool details
    _contribution_counter = 0
    _reward_counter = 0
    _transaction_counter = 0

    # Configuration
    BASE_TASK_REWARD = 10.0
    QUALITY_MULTIPLIER = 1.5
    COLLABORATION_BONUS = 5.0
    STREAK_BONUS_PER_DAY = 2.0

    @staticmethod
    def initialize_agent(
        session: Session,
        agent_id: int,
        initial_balance: float = 0.0
    ) -> Dict[str, Any]:
        """
        Initialize incentive tracking for an agent.

        Args:
            session: Database session
            agent_id: Agent ID
            initial_balance: Starting balance

        Returns:
            Agent balance details
        """
        # Validate agent
        agent = session.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        if agent_id in AgentIncentive._agent_balances:
            raise ValueError(f"Agent {agent_id} already initialized")

        AgentIncentive._agent_balances[agent_id] = initial_balance
        AgentIncentive._contributions[agent_id] = []
        AgentIncentive._rewards[agent_id] = []

        logger.info(f"Initialized incentives for agent {agent_id} with balance {initial_balance}")

        return {
            "agent_id": agent_id,
            "agent_name": agent.name,
            "balance": initial_balance,
            "total_contributions": 0,
            "total_rewards": 0,
            "initialized_at": datetime.utcnow().isoformat()
        }

    @staticmethod
    def record_contribution(
        session: Session,
        agent_id: int,
        contribution_type: str,
        value: float,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Record a contribution from an agent.

        Args:
            session: Database session
            agent_id: Agent ID
            contribution_type: Type of contribution
            value: Contribution value/weight
            description: Description of contribution
            metadata: Optional metadata

        Returns:
            Contribution details
        """
        if agent_id not in AgentIncentive._agent_balances:
            raise ValueError(f"Agent {agent_id} not initialized")

        AgentIncentive._contribution_counter += 1
        contribution = {
            "contribution_id": AgentIncentive._contribution_counter,
            "agent_id": agent_id,
            "contribution_type": contribution_type,
            "value": value,
            "description": description,
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat()
        }

        AgentIncentive._contributions[agent_id].append(contribution)

        logger.info(
            f"Recorded contribution for agent {agent_id}: {contribution_type} "
            f"(value: {value})"
        )

        return contribution

    @staticmethod
    def calculate_task_reward(
        session: Session,
        agent_id: int,
        task_id: int,
        completion_time_hours: float,
        quality_score: float = 1.0,
        difficulty_multiplier: float = 1.0
    ) -> Dict[str, Any]:
        """
        Calculate reward for task completion.

        Args:
            session: Database session
            agent_id: Agent ID
            task_id: Task ID
            completion_time_hours: Time taken to complete
            quality_score: Quality rating (0-1)
            difficulty_multiplier: Task difficulty (1.0 = normal)

        Returns:
            Reward calculation details
        """
        if agent_id not in AgentIncentive._agent_balances:
            raise ValueError(f"Agent {agent_id} not initialized")

        # Base reward
        base_reward = AgentIncentive.BASE_TASK_REWARD * difficulty_multiplier

        # Quality bonus
        quality_bonus = 0.0
        if quality_score > 0.8:
            quality_bonus = base_reward * (quality_score - 0.8) * AgentIncentive.QUALITY_MULTIPLIER

        # Speed bonus (if completed faster than expected)
        speed_bonus = 0.0
        expected_time = 8.0 * difficulty_multiplier  # 8 hours base
        if completion_time_hours < expected_time:
            time_saved_ratio = (expected_time - completion_time_hours) / expected_time
            speed_bonus = base_reward * time_saved_ratio * 0.5

        # Total reward
        total_reward = base_reward + quality_bonus + speed_bonus

        calculation = {
            "agent_id": agent_id,
            "task_id": task_id,
            "base_reward": base_reward,
            "quality_bonus": quality_bonus,
            "speed_bonus": speed_bonus,
            "total_reward": total_reward,
            "breakdown": {
                "difficulty_multiplier": difficulty_multiplier,
                "quality_score": quality_score,
                "completion_time_hours": completion_time_hours,
                "expected_time_hours": expected_time
            }
        }

        logger.info(
            f"Calculated task reward for agent {agent_id}: {total_reward:.2f} "
            f"(base: {base_reward:.2f}, quality: {quality_bonus:.2f}, speed: {speed_bonus:.2f})"
        )

        return calculation

    @staticmethod
    def award_reward(
        session: Session,
        agent_id: int,
        reward_type: str,
        amount: float,
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        auto_approve: bool = True
    ) -> Dict[str, Any]:
        """
        Award a reward to an agent.

        Args:
            session: Database session
            agent_id: Agent ID
            reward_type: Type of reward
            amount: Reward amount
            reason: Reason for reward
            metadata: Optional metadata
            auto_approve: Auto-approve and distribute

        Returns:
            Reward details
        """
        if agent_id not in AgentIncentive._agent_balances:
            raise ValueError(f"Agent {agent_id} not initialized")

        if amount < 0:
            raise ValueError("Reward amount must be non-negative")

        AgentIncentive._reward_counter += 1
        reward = {
            "reward_id": AgentIncentive._reward_counter,
            "agent_id": agent_id,
            "reward_type": reward_type,
            "amount": amount,
            "reason": reason,
            "status": RewardStatus.APPROVED if auto_approve else RewardStatus.PENDING,
            "metadata": metadata or {},
            "created_at": datetime.utcnow().isoformat(),
            "approved_at": datetime.utcnow().isoformat() if auto_approve else None,
            "distributed_at": None
        }

        AgentIncentive._rewards[agent_id].append(reward)

        # Auto-distribute if approved
        if auto_approve:
            AgentIncentive._distribute_reward(agent_id, reward)

        logger.info(
            f"Awarded {amount:.2f} to agent {agent_id}: {reward_type} "
            f"(status: {reward['status']})"
        )

        return reward

    @staticmethod
    def _distribute_reward(agent_id: int, reward: Dict[str, Any]):
        """Distribute an approved reward to agent's balance"""
        AgentIncentive._agent_balances[agent_id] += reward["amount"]
        reward["status"] = RewardStatus.DISTRIBUTED
        reward["distributed_at"] = datetime.utcnow().isoformat()

        # Record transaction
        AgentIncentive._transaction_counter += 1
        transaction = {
            "transaction_id": AgentIncentive._transaction_counter,
            "agent_id": agent_id,
            "type": "reward",
            "amount": reward["amount"],
            "reward_id": reward["reward_id"],
            "balance_after": AgentIncentive._agent_balances[agent_id],
            "timestamp": datetime.utcnow().isoformat()
        }
        AgentIncentive._transactions.append(transaction)

    @staticmethod
    def transfer_balance(
        session: Session,
        from_agent_id: int,
        to_agent_id: int,
        amount: float,
        reason: str = ""
    ) -> Dict[str, Any]:
        """
        Transfer balance between agents.

        Args:
            session: Database session
            from_agent_id: Sender agent ID
            to_agent_id: Receiver agent ID
            amount: Transfer amount
            reason: Transfer reason

        Returns:
            Transfer details
        """
        if from_agent_id not in AgentIncentive._agent_balances:
            raise ValueError(f"Sender agent {from_agent_id} not initialized")

        if to_agent_id not in AgentIncentive._agent_balances:
            raise ValueError(f"Receiver agent {to_agent_id} not initialized")

        if amount <= 0:
            raise ValueError("Transfer amount must be positive")

        if AgentIncentive._agent_balances[from_agent_id] < amount:
            raise ValueError(
                f"Insufficient balance: {AgentIncentive._agent_balances[from_agent_id]} < {amount}"
            )

        # Perform transfer
        AgentIncentive._agent_balances[from_agent_id] -= amount
        AgentIncentive._agent_balances[to_agent_id] += amount

        # Record transactions
        AgentIncentive._transaction_counter += 1
        debit_transaction = {
            "transaction_id": AgentIncentive._transaction_counter,
            "agent_id": from_agent_id,
            "type": "transfer_out",
            "amount": -amount,
            "to_agent_id": to_agent_id,
            "reason": reason,
            "balance_after": AgentIncentive._agent_balances[from_agent_id],
            "timestamp": datetime.utcnow().isoformat()
        }
        AgentIncentive._transactions.append(debit_transaction)

        AgentIncentive._transaction_counter += 1
        credit_transaction = {
            "transaction_id": AgentIncentive._transaction_counter,
            "agent_id": to_agent_id,
            "type": "transfer_in",
            "amount": amount,
            "from_agent_id": from_agent_id,
            "reason": reason,
            "balance_after": AgentIncentive._agent_balances[to_agent_id],
            "timestamp": datetime.utcnow().isoformat()
        }
        AgentIncentive._transactions.append(credit_transaction)

        logger.info(f"Transferred {amount:.2f} from agent {from_agent_id} to {to_agent_id}")

        return {
            "from_agent_id": from_agent_id,
            "to_agent_id": to_agent_id,
            "amount": amount,
            "reason": reason,
            "from_balance": AgentIncentive._agent_balances[from_agent_id],
            "to_balance": AgentIncentive._agent_balances[to_agent_id],
            "timestamp": datetime.utcnow().isoformat()
        }

    @staticmethod
    def create_reward_pool(
        session: Session,
        pool_name: str,
        total_amount: float,
        distribution_criteria: Dict[str, Any],
        deadline: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Create a reward pool for distribution.

        Args:
            session: Database session
            pool_name: Pool name
            total_amount: Total pool amount
            distribution_criteria: Criteria for distribution
            deadline: Optional distribution deadline

        Returns:
            Pool details
        """
        pool_id = f"pool_{len(AgentIncentive._reward_pools) + 1}"

        pool = {
            "pool_id": pool_id,
            "pool_name": pool_name,
            "total_amount": total_amount,
            "distributed_amount": 0.0,
            "remaining_amount": total_amount,
            "distribution_criteria": distribution_criteria,
            "deadline": deadline.isoformat() if deadline else None,
            "created_at": datetime.utcnow().isoformat(),
            "status": "active"
        }

        AgentIncentive._reward_pools[pool_id] = pool

        logger.info(f"Created reward pool '{pool_name}' with {total_amount:.2f}")

        return pool

    @staticmethod
    def distribute_from_pool(
        session: Session,
        pool_id: str,
        agent_rewards: Dict[int, float]
    ) -> Dict[str, Any]:
        """
        Distribute rewards from a pool to multiple agents.

        Args:
            session: Database session
            pool_id: Pool ID
            agent_rewards: Mapping of agent_id to reward amount

        Returns:
            Distribution details
        """
        if pool_id not in AgentIncentive._reward_pools:
            raise ValueError(f"Pool {pool_id} not found")

        pool = AgentIncentive._reward_pools[pool_id]

        if pool["status"] != "active":
            raise ValueError(f"Pool {pool_id} is not active")

        # Calculate total distribution
        total_distribution = sum(agent_rewards.values())

        if total_distribution > pool["remaining_amount"]:
            raise ValueError(
                f"Distribution amount {total_distribution} exceeds remaining pool amount "
                f"{pool['remaining_amount']}"
            )

        # Distribute to agents
        distributed = []
        for agent_id, amount in agent_rewards.items():
            if agent_id not in AgentIncentive._agent_balances:
                raise ValueError(f"Agent {agent_id} not initialized")

            reward = AgentIncentive.award_reward(
                session=session,
                agent_id=agent_id,
                reward_type=RewardType.MILESTONE_REWARD,
                amount=amount,
                reason=f"Distribution from pool '{pool['pool_name']}'",
                metadata={"pool_id": pool_id}
            )

            distributed.append({
                "agent_id": agent_id,
                "amount": amount,
                "reward_id": reward["reward_id"]
            })

        # Update pool
        pool["distributed_amount"] += total_distribution
        pool["remaining_amount"] -= total_distribution

        if pool["remaining_amount"] <= 0:
            pool["status"] = "depleted"

        logger.info(
            f"Distributed {total_distribution:.2f} from pool '{pool['pool_name']}' "
            f"to {len(agent_rewards)} agents"
        )

        return {
            "pool_id": pool_id,
            "total_distributed": total_distribution,
            "agents_rewarded": len(agent_rewards),
            "distributed": distributed,
            "pool_remaining": pool["remaining_amount"]
        }

    @staticmethod
    def get_agent_balance(
        session: Session,
        agent_id: int
    ) -> Dict[str, Any]:
        """Get agent's current balance and summary"""
        if agent_id not in AgentIncentive._agent_balances:
            raise ValueError(f"Agent {agent_id} not initialized")

        contributions = AgentIncentive._contributions.get(agent_id, [])
        rewards = AgentIncentive._rewards.get(agent_id, [])

        total_rewards = sum(r["amount"] for r in rewards if r["status"] == RewardStatus.DISTRIBUTED)
        pending_rewards = sum(r["amount"] for r in rewards if r["status"] == RewardStatus.PENDING)

        return {
            "agent_id": agent_id,
            "current_balance": AgentIncentive._agent_balances[agent_id],
            "total_rewards_received": total_rewards,
            "pending_rewards": pending_rewards,
            "total_contributions": len(contributions),
            "total_contribution_value": sum(c["value"] for c in contributions)
        }

    @staticmethod
    def get_leaderboard(
        session: Session,
        metric: str = "balance",
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Get leaderboard of top agents.

        Args:
            session: Database session
            metric: Metric to rank by (balance/contributions/rewards)
            limit: Maximum agents to return

        Returns:
            Leaderboard
        """
        agents = []

        for agent_id in AgentIncentive._agent_balances.keys():
            agent = session.query(Agent).filter(Agent.id == agent_id).first()
            if not agent:
                continue

            contributions = AgentIncentive._contributions.get(agent_id, [])
            rewards = AgentIncentive._rewards.get(agent_id, [])

            total_rewards = sum(
                r["amount"] for r in rewards if r["status"] == RewardStatus.DISTRIBUTED
            )

            agent_data = {
                "agent_id": agent_id,
                "agent_name": agent.name,
                "balance": AgentIncentive._agent_balances[agent_id],
                "total_contributions": len(contributions),
                "total_rewards": total_rewards
            }

            agents.append(agent_data)

        # Sort by metric
        if metric == "balance":
            agents.sort(key=lambda x: x["balance"], reverse=True)
        elif metric == "contributions":
            agents.sort(key=lambda x: x["total_contributions"], reverse=True)
        elif metric == "rewards":
            agents.sort(key=lambda x: x["total_rewards"], reverse=True)
        else:
            raise ValueError(f"Invalid metric: {metric}")

        return {
            "metric": metric,
            "total_agents": len(agents),
            "leaderboard": agents[:limit]
        }

    @staticmethod
    def get_incentive_statistics(session: Session) -> Dict[str, Any]:
        """
        Get incentive system statistics.

        Args:
            session: Database session

        Returns:
            System statistics
        """
        total_agents = len(AgentIncentive._agent_balances)
        total_balance = sum(AgentIncentive._agent_balances.values())

        total_contributions = sum(
            len(contributions) for contributions in AgentIncentive._contributions.values()
        )

        all_rewards = []
        for rewards in AgentIncentive._rewards.values():
            all_rewards.extend(rewards)

        distributed_rewards = [r for r in all_rewards if r["status"] == RewardStatus.DISTRIBUTED]
        pending_rewards = [r for r in all_rewards if r["status"] == RewardStatus.PENDING]

        total_distributed = sum(r["amount"] for r in distributed_rewards)
        total_pending = sum(r["amount"] for r in pending_rewards)

        # Rewards by type
        rewards_by_type = {}
        for reward in distributed_rewards:
            reward_type = reward["reward_type"]
            rewards_by_type[reward_type] = rewards_by_type.get(reward_type, 0) + reward["amount"]

        # Active pools
        active_pools = [p for p in AgentIncentive._reward_pools.values() if p["status"] == "active"]

        return {
            "total_agents": total_agents,
            "total_system_balance": total_balance,
            "total_contributions": total_contributions,
            "total_rewards_distributed": total_distributed,
            "total_rewards_pending": total_pending,
            "total_transactions": len(AgentIncentive._transactions),
            "rewards_by_type": rewards_by_type,
            "active_reward_pools": len(active_pools),
            "total_pool_value": sum(p["remaining_amount"] for p in active_pools)
        }

    @staticmethod
    def get_agent_history(
        session: Session,
        agent_id: int,
        limit: int = 50
    ) -> Dict[str, Any]:
        """Get agent's contribution and reward history"""
        if agent_id not in AgentIncentive._agent_balances:
            raise ValueError(f"Agent {agent_id} not initialized")

        contributions = AgentIncentive._contributions.get(agent_id, [])
        rewards = AgentIncentive._rewards.get(agent_id, [])
        transactions = [
            t for t in AgentIncentive._transactions
            if t["agent_id"] == agent_id
        ]

        # Sort by timestamp descending
        contributions_sorted = sorted(
            contributions,
            key=lambda x: x["created_at"],
            reverse=True
        )[:limit]

        rewards_sorted = sorted(
            rewards,
            key=lambda x: x["created_at"],
            reverse=True
        )[:limit]

        transactions_sorted = sorted(
            transactions,
            key=lambda x: x["timestamp"],
            reverse=True
        )[:limit]

        return {
            "agent_id": agent_id,
            "recent_contributions": contributions_sorted,
            "recent_rewards": rewards_sorted,
            "recent_transactions": transactions_sorted
        }
