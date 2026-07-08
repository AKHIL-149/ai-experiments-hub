"""
Agent Knowledge Sharing Service

Enables agents to share, discover, and validate knowledge through a collaborative knowledge base.
Supports knowledge items, queries, ratings, versioning, and effectiveness tracking.
"""

from typing import Dict, List, Optional
from datetime import datetime, timedelta
from collections import defaultdict


class KnowledgeType:
    """Types of knowledge that can be shared"""
    FACT = "fact"
    PROCEDURE = "procedure"
    BEST_PRACTICE = "best_practice"
    SOLUTION = "solution"
    PATTERN = "pattern"
    WARNING = "warning"
    TIP = "tip"


class KnowledgeCategory:
    """Categories for organizing knowledge"""
    TECHNICAL = "technical"
    PROCESS = "process"
    DOMAIN = "domain"
    COLLABORATION = "collaboration"
    STRATEGY = "strategy"
    TOOLING = "tooling"
    GENERAL = "general"


class ValidationStatus:
    """Knowledge validation statuses"""
    UNVALIDATED = "unvalidated"
    PENDING = "pending"
    VALIDATED = "validated"
    DISPUTED = "disputed"
    DEPRECATED = "deprecated"


class AccessLevel:
    """Knowledge access levels"""
    PUBLIC = "public"
    COALITION = "coalition"
    TRUSTED = "trusted"
    PRIVATE = "private"


class AgentKnowledge:
    """
    Agent Knowledge Sharing System

    Manages shared knowledge base, queries, ratings, and validation.
    Enables collaborative learning through knowledge exchange.
    """

    # In-memory storage
    _knowledge_items = {}
    _item_counter = 0

    _agent_knowledge = defaultdict(list)  # agent_id -> [knowledge_item_ids]
    _knowledge_queries = {}
    _query_counter = 0

    _knowledge_ratings = defaultdict(list)  # item_id -> [ratings]
    _knowledge_validations = defaultdict(list)  # item_id -> [validations]
    _knowledge_usage = defaultdict(list)  # item_id -> [usage_records]

    _knowledge_subscriptions = defaultdict(list)  # agent_id -> [category/tag subscriptions]

    @staticmethod
    def share_knowledge(
        session,
        agent_id: int,
        knowledge_type: str,
        category: str,
        title: str,
        content: dict,
        tags: Optional[List[str]] = None,
        access_level: str = AccessLevel.PUBLIC,
        source: Optional[str] = None,
        confidence: float = 0.8,
        metadata: Optional[dict] = None
    ) -> dict:
        """
        Share a knowledge item.

        Args:
            session: Database session
            agent_id: Agent sharing knowledge
            knowledge_type: Type of knowledge
            category: Knowledge category
            title: Knowledge title
            content: Knowledge content (structure varies by type)
            tags: Optional tags for categorization
            access_level: Who can access this knowledge
            source: Optional source reference
            confidence: Confidence in knowledge accuracy (0-1)
            metadata: Additional metadata

        Returns:
            Knowledge item dictionary
        """
        AgentKnowledge._item_counter += 1
        item_id = f"knowledge_{AgentKnowledge._item_counter}"

        knowledge_item = {
            "id": item_id,
            "agent_id": agent_id,
            "knowledge_type": knowledge_type,
            "category": category,
            "title": title,
            "content": content,
            "tags": tags or [],
            "access_level": access_level,
            "source": source,
            "confidence": confidence,
            "validation_status": ValidationStatus.UNVALIDATED,
            "version": 1,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
            "usage_count": 0,
            "average_rating": 0.0,
            "validation_count": 0
        }

        AgentKnowledge._knowledge_items[item_id] = knowledge_item
        AgentKnowledge._agent_knowledge[agent_id].append(item_id)

        # Notify subscribers
        AgentKnowledge._notify_subscribers(category, tags or [], knowledge_item)

        return knowledge_item

    @staticmethod
    def query_knowledge(
        session,
        agent_id: int,
        query_text: str,
        categories: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        knowledge_types: Optional[List[str]] = None,
        min_confidence: float = 0.5,
        min_rating: float = 0.0,
        validated_only: bool = False,
        limit: int = 10
    ) -> dict:
        """
        Query the knowledge base.

        Args:
            session: Database session
            agent_id: Agent making query
            query_text: Search query
            categories: Filter by categories
            tags: Filter by tags
            knowledge_types: Filter by knowledge types
            min_confidence: Minimum confidence threshold
            min_rating: Minimum average rating
            validated_only: Only return validated knowledge
            limit: Maximum results to return

        Returns:
            Query results with matched items
        """
        AgentKnowledge._query_counter += 1
        query_id = f"query_{AgentKnowledge._query_counter}"

        # Filter knowledge items
        results = []
        for item_id, item in AgentKnowledge._knowledge_items.items():
            # Access control
            if not AgentKnowledge._can_access(agent_id, item):
                continue

            # Apply filters
            if categories and item["category"] not in categories:
                continue
            if knowledge_types and item["knowledge_type"] not in knowledge_types:
                continue
            if item["confidence"] < min_confidence:
                continue
            if item["average_rating"] < min_rating:
                continue
            if validated_only and item["validation_status"] != ValidationStatus.VALIDATED:
                continue

            # Tag matching
            if tags:
                if not any(tag in item["tags"] for tag in tags):
                    continue

            # Simple text matching in title and content
            query_lower = query_text.lower()
            title_match = query_lower in item["title"].lower()
            content_match = AgentKnowledge._search_content(query_lower, item["content"])

            if title_match or content_match:
                # Calculate relevance score
                relevance = 0.0
                if title_match:
                    relevance += 0.6
                if content_match:
                    relevance += 0.4

                # Boost by rating and confidence
                relevance *= (item["average_rating"] / 5.0 + 1) / 2  # Rating boost
                relevance *= item["confidence"]  # Confidence boost

                results.append({
                    **item,
                    "relevance_score": relevance
                })

        # Sort by relevance
        results.sort(key=lambda x: x["relevance_score"], reverse=True)
        results = results[:limit]

        # Record query
        query_record = {
            "id": query_id,
            "agent_id": agent_id,
            "query_text": query_text,
            "filters": {
                "categories": categories,
                "tags": tags,
                "knowledge_types": knowledge_types,
                "min_confidence": min_confidence,
                "min_rating": min_rating,
                "validated_only": validated_only
            },
            "results_count": len(results),
            "timestamp": datetime.utcnow().isoformat()
        }
        AgentKnowledge._knowledge_queries[query_id] = query_record

        return {
            "query_id": query_id,
            "results": results,
            "total_found": len(results)
        }

    @staticmethod
    def rate_knowledge(
        session,
        item_id: str,
        agent_id: int,
        rating: float,
        comment: str = "",
        helpful: bool = True
    ) -> dict:
        """
        Rate a knowledge item.

        Args:
            session: Database session
            item_id: Knowledge item ID
            agent_id: Agent giving rating
            rating: Rating value (1-5)
            comment: Optional comment
            helpful: Whether item was helpful

        Returns:
            Rating record
        """
        if item_id not in AgentKnowledge._knowledge_items:
            raise ValueError(f"Knowledge item {item_id} not found")

        if not 1 <= rating <= 5:
            raise ValueError("Rating must be between 1 and 5")

        rating_record = {
            "item_id": item_id,
            "agent_id": agent_id,
            "rating": rating,
            "comment": comment,
            "helpful": helpful,
            "timestamp": datetime.utcnow().isoformat()
        }

        AgentKnowledge._knowledge_ratings[item_id].append(rating_record)

        # Update average rating
        ratings = AgentKnowledge._knowledge_ratings[item_id]
        avg_rating = sum(r["rating"] for r in ratings) / len(ratings)
        AgentKnowledge._knowledge_items[item_id]["average_rating"] = avg_rating

        return rating_record

    @staticmethod
    def validate_knowledge(
        session,
        item_id: str,
        validator_agent_id: int,
        is_valid: bool,
        validation_notes: str = "",
        evidence: Optional[dict] = None
    ) -> dict:
        """
        Validate or dispute knowledge.

        Args:
            session: Database session
            item_id: Knowledge item ID
            validator_agent_id: Agent performing validation
            is_valid: Whether knowledge is valid
            validation_notes: Notes about validation
            evidence: Optional supporting evidence

        Returns:
            Validation record
        """
        if item_id not in AgentKnowledge._knowledge_items:
            raise ValueError(f"Knowledge item {item_id} not found")

        validation = {
            "item_id": item_id,
            "validator_agent_id": validator_agent_id,
            "is_valid": is_valid,
            "validation_notes": validation_notes,
            "evidence": evidence or {},
            "timestamp": datetime.utcnow().isoformat()
        }

        AgentKnowledge._knowledge_validations[item_id].append(validation)

        # Update validation status
        validations = AgentKnowledge._knowledge_validations[item_id]
        valid_count = sum(1 for v in validations if v["is_valid"])
        invalid_count = len(validations) - valid_count

        item = AgentKnowledge._knowledge_items[item_id]

        if valid_count >= 3:
            item["validation_status"] = ValidationStatus.VALIDATED
        elif invalid_count >= 2:
            item["validation_status"] = ValidationStatus.DISPUTED
        else:
            item["validation_status"] = ValidationStatus.PENDING

        item["validation_count"] = len(validations)

        return validation

    @staticmethod
    def record_usage(
        session,
        item_id: str,
        agent_id: int,
        usage_context: dict,
        was_useful: bool,
        outcome: str = ""
    ) -> dict:
        """
        Record knowledge usage.

        Args:
            session: Database session
            item_id: Knowledge item ID
            agent_id: Agent using knowledge
            usage_context: Context of usage
            was_useful: Whether knowledge was useful
            outcome: Outcome description

        Returns:
            Usage record
        """
        if item_id not in AgentKnowledge._knowledge_items:
            raise ValueError(f"Knowledge item {item_id} not found")

        usage = {
            "item_id": item_id,
            "agent_id": agent_id,
            "usage_context": usage_context,
            "was_useful": was_useful,
            "outcome": outcome,
            "timestamp": datetime.utcnow().isoformat()
        }

        AgentKnowledge._knowledge_usage[item_id].append(usage)

        # Update usage count
        AgentKnowledge._knowledge_items[item_id]["usage_count"] += 1

        return usage

    @staticmethod
    def update_knowledge(
        session,
        item_id: str,
        agent_id: int,
        updates: dict,
        update_reason: str = ""
    ) -> dict:
        """
        Update existing knowledge item.

        Args:
            session: Database session
            item_id: Knowledge item ID
            agent_id: Agent making update
            updates: Fields to update
            update_reason: Reason for update

        Returns:
            Updated knowledge item
        """
        if item_id not in AgentKnowledge._knowledge_items:
            raise ValueError(f"Knowledge item {item_id} not found")

        item = AgentKnowledge._knowledge_items[item_id]

        # Only creator or high-reputation agents can update
        if item["agent_id"] != agent_id:
            raise ValueError("Only knowledge creator can update")

        # Update allowed fields
        allowed_fields = ["title", "content", "tags", "confidence", "category"]
        for field in allowed_fields:
            if field in updates:
                item[field] = updates[field]

        # Increment version
        item["version"] += 1
        item["updated_at"] = datetime.utcnow().isoformat()

        # Reset validation status if content changed
        if "content" in updates:
            item["validation_status"] = ValidationStatus.UNVALIDATED

        return item

    @staticmethod
    def subscribe_to_category(
        session,
        agent_id: int,
        category: str = None,
        tags: Optional[List[str]] = None
    ) -> dict:
        """
        Subscribe to knowledge updates.

        Args:
            session: Database session
            agent_id: Agent subscribing
            category: Category to subscribe to
            tags: Tags to subscribe to

        Returns:
            Subscription record
        """
        subscription = {
            "agent_id": agent_id,
            "category": category,
            "tags": tags or [],
            "subscribed_at": datetime.utcnow().isoformat()
        }

        AgentKnowledge._knowledge_subscriptions[agent_id].append(subscription)

        return subscription

    @staticmethod
    def get_knowledge_item(session, item_id: str) -> dict:
        """
        Get knowledge item details.

        Args:
            session: Database session
            item_id: Knowledge item ID

        Returns:
            Knowledge item with ratings and validations
        """
        if item_id not in AgentKnowledge._knowledge_items:
            raise ValueError(f"Knowledge item {item_id} not found")

        item = AgentKnowledge._knowledge_items[item_id]
        ratings = AgentKnowledge._knowledge_ratings.get(item_id, [])
        validations = AgentKnowledge._knowledge_validations.get(item_id, [])
        usage_records = AgentKnowledge._knowledge_usage.get(item_id, [])

        # Calculate effectiveness
        if usage_records:
            useful_count = sum(1 for u in usage_records if u["was_useful"])
            effectiveness = useful_count / len(usage_records)
        else:
            effectiveness = 0.0

        return {
            **item,
            "ratings": ratings,
            "validations": validations,
            "usage_records": usage_records[-10:],  # Last 10 usages
            "effectiveness": effectiveness
        }

    @staticmethod
    def get_agent_knowledge(
        session,
        agent_id: int,
        include_shared: bool = True,
        include_accessed: bool = True
    ) -> dict:
        """
        Get agent's knowledge activity.

        Args:
            session: Database session
            agent_id: Agent ID
            include_shared: Include knowledge shared by agent
            include_accessed: Include knowledge accessed by agent

        Returns:
            Agent's knowledge activity
        """
        result = {
            "agent_id": agent_id,
            "shared_knowledge": [],
            "accessed_knowledge": [],
            "queries": []
        }

        if include_shared:
            item_ids = AgentKnowledge._agent_knowledge.get(agent_id, [])
            result["shared_knowledge"] = [
                AgentKnowledge._knowledge_items[iid]
                for iid in item_ids
                if iid in AgentKnowledge._knowledge_items
            ]

        if include_accessed:
            # Find items rated or used by this agent
            accessed = set()
            for item_id, ratings in AgentKnowledge._knowledge_ratings.items():
                if any(r["agent_id"] == agent_id for r in ratings):
                    accessed.add(item_id)
            for item_id, usages in AgentKnowledge._knowledge_usage.items():
                if any(u["agent_id"] == agent_id for u in usages):
                    accessed.add(item_id)

            result["accessed_knowledge"] = [
                AgentKnowledge._knowledge_items[iid]
                for iid in accessed
                if iid in AgentKnowledge._knowledge_items
            ]

        # Get queries
        result["queries"] = [
            q for q in AgentKnowledge._knowledge_queries.values()
            if q["agent_id"] == agent_id
        ]

        return result

    @staticmethod
    def get_trending_knowledge(
        session,
        timeframe_hours: int = 24,
        limit: int = 10
    ) -> dict:
        """
        Get trending knowledge items.

        Args:
            session: Database session
            timeframe_hours: Time window for trending calculation
            limit: Maximum items to return

        Returns:
            Trending knowledge items
        """
        cutoff = datetime.utcnow() - timedelta(hours=timeframe_hours)
        cutoff_iso = cutoff.isoformat()

        trending = []
        for item_id, item in AgentKnowledge._knowledge_items.items():
            # Count recent activity
            recent_ratings = sum(
                1 for r in AgentKnowledge._knowledge_ratings.get(item_id, [])
                if r["timestamp"] > cutoff_iso
            )
            recent_usages = sum(
                1 for u in AgentKnowledge._knowledge_usage.get(item_id, [])
                if u["timestamp"] > cutoff_iso
            )

            activity_score = recent_ratings * 2 + recent_usages

            if activity_score > 0:
                trending.append({
                    **item,
                    "activity_score": activity_score,
                    "recent_ratings": recent_ratings,
                    "recent_usages": recent_usages
                })

        # Sort by activity score
        trending.sort(key=lambda x: x["activity_score"], reverse=True)

        return {
            "timeframe_hours": timeframe_hours,
            "trending_items": trending[:limit]
        }

    @staticmethod
    def get_knowledge_statistics(session) -> dict:
        """
        Get knowledge system statistics.

        Args:
            session: Database session

        Returns:
            System statistics
        """
        total_items = len(AgentKnowledge._knowledge_items)

        # Count by type
        by_type = defaultdict(int)
        by_category = defaultdict(int)
        by_status = defaultdict(int)

        for item in AgentKnowledge._knowledge_items.values():
            by_type[item["knowledge_type"]] += 1
            by_category[item["category"]] += 1
            by_status[item["validation_status"]] += 1

        # Rating statistics
        all_ratings = [r for ratings in AgentKnowledge._knowledge_ratings.values() for r in ratings]
        avg_rating = sum(r["rating"] for r in all_ratings) / len(all_ratings) if all_ratings else 0

        # Usage statistics
        all_usages = [u for usages in AgentKnowledge._knowledge_usage.values() for u in usages]
        useful_usages = sum(1 for u in all_usages if u["was_useful"])
        overall_effectiveness = useful_usages / len(all_usages) if all_usages else 0

        return {
            "total_knowledge_items": total_items,
            "total_ratings": len(all_ratings),
            "total_validations": sum(len(v) for v in AgentKnowledge._knowledge_validations.values()),
            "total_usages": len(all_usages),
            "total_queries": len(AgentKnowledge._knowledge_queries),
            "by_type": dict(by_type),
            "by_category": dict(by_category),
            "by_validation_status": dict(by_status),
            "average_rating": avg_rating,
            "overall_effectiveness": overall_effectiveness,
            "unique_contributors": len(AgentKnowledge._agent_knowledge),
            "total_subscriptions": sum(len(s) for s in AgentKnowledge._knowledge_subscriptions.values())
        }

    # Helper methods

    @staticmethod
    def _can_access(agent_id: int, item: dict) -> bool:
        """Check if agent can access knowledge item"""
        access_level = item["access_level"]

        if access_level == AccessLevel.PUBLIC:
            return True
        elif access_level == AccessLevel.PRIVATE:
            return agent_id == item["agent_id"]
        # For COALITION and TRUSTED, would need additional context
        # For now, allow access
        return True

    @staticmethod
    def _search_content(query: str, content: dict) -> bool:
        """Search within content dictionary"""
        content_str = str(content).lower()
        return query in content_str

    @staticmethod
    def _notify_subscribers(category: str, tags: List[str], item: dict):
        """Notify subscribed agents of new knowledge"""
        # In a real system, would send notifications
        # For now, just track that it happened
        pass
