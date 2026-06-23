"""
Team Management Service - Create and manage teams, members, and invitations
"""

import secrets
import uuid
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy import and_, or_

from src.core.database import (
    DatabaseManager, Team, TeamMember, TeamInvitation,
    User, CustomRule, Plugin, Repository
)


class TeamService:
    """Service for managing teams and team memberships."""

    def create_team(self, name: str, slug: str, user_id: str,
                   description: Optional[str] = None,
                   visibility: str = 'private') -> Dict[str, Any]:
        """
        Create a new team.

        Args:
            name: Team name
            slug: URL-friendly identifier
            user_id: User ID creating the team (becomes owner)
            description: Optional team description
            visibility: Team visibility (private/public)

        Returns:
            Result dictionary with team and membership
        """
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            # Check if slug is already taken
            existing = db.query(Team).filter(Team.slug == slug).first()
            if existing:
                return {
                    'success': False,
                    'error': 'Team slug already exists'
                }

            # Create team
            team = Team(
                name=name,
                slug=slug,
                description=description,
                visibility=visibility,
                member_count=1
            )

            db.add(team)
            db.flush()  # Get team ID

            # Add creator as owner
            owner = TeamMember(
                team_id=team.id,
                user_id=user_id,
                role='owner',
                can_manage_members=True,
                can_manage_settings=True,
                can_create_rules=True,
                can_manage_plugins=True
            )

            db.add(owner)
            db.commit()
            db.refresh(team)
            db.refresh(owner)

            return {
                'success': True,
                'team': team.to_dict(),
                'membership': owner.to_dict()
            }

    def get_team(self, team_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get team by ID.

        Args:
            team_id: Team ID
            user_id: Optional user ID for membership check

        Returns:
            Team dictionary or None
        """
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            team = db.query(Team).filter(Team.id == team_id).first()

            if not team:
                return None

            team_dict = team.to_dict()

            # If user_id provided, check membership
            if user_id:
                member = db.query(TeamMember).filter(
                    TeamMember.team_id == team_id,
                    TeamMember.user_id == user_id
                ).first()

                team_dict['is_member'] = member is not None
                team_dict['role'] = member.role if member else None
                team_dict['permissions'] = member.to_dict() if member else None

            return team_dict

    def get_team_by_slug(self, slug: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get team by slug.

        Args:
            slug: Team slug
            user_id: Optional user ID for membership check

        Returns:
            Team dictionary or None
        """
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            team = db.query(Team).filter(Team.slug == slug).first()

            if not team:
                return None

            return self.get_team(team.id, user_id)

    def update_team(self, team_id: str, user_id: str, **kwargs) -> Dict[str, Any]:
        """
        Update team settings.

        Args:
            team_id: Team ID
            user_id: User ID (must have permissions)
            **kwargs: Fields to update

        Returns:
            Result dictionary
        """
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            # Check permissions
            member = db.query(TeamMember).filter(
                TeamMember.team_id == team_id,
                TeamMember.user_id == user_id
            ).first()

            if not member or not member.can_manage_settings:
                return {
                    'success': False,
                    'error': 'Insufficient permissions'
                }

            team = db.query(Team).filter(Team.id == team_id).first()
            if not team:
                return {
                    'success': False,
                    'error': 'Team not found'
                }

            # Update allowed fields
            allowed_fields = ['name', 'description', 'visibility', 'allow_member_invites']
            for field in allowed_fields:
                if field in kwargs:
                    setattr(team, field, kwargs[field])

            team.updated_at = datetime.now(timezone.utc)
            db.commit()
            db.refresh(team)

            return {
                'success': True,
                'team': team.to_dict()
            }

    def delete_team(self, team_id: str, user_id: str) -> Dict[str, Any]:
        """
        Delete a team (only owner can delete).

        Args:
            team_id: Team ID
            user_id: User ID (must be owner)

        Returns:
            Result dictionary
        """
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            # Check if user is owner
            member = db.query(TeamMember).filter(
                TeamMember.team_id == team_id,
                TeamMember.user_id == user_id,
                TeamMember.role == 'owner'
            ).first()

            if not member:
                return {
                    'success': False,
                    'error': 'Only team owner can delete the team'
                }

            team = db.query(Team).filter(Team.id == team_id).first()
            if not team:
                return {
                    'success': False,
                    'error': 'Team not found'
                }

            db.delete(team)
            db.commit()

            return {
                'success': True,
                'message': 'Team deleted successfully'
            }

    def get_team_members(self, team_id: str, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """
        Get all team members.

        Args:
            team_id: Team ID
            include_inactive: Include inactive members

        Returns:
            List of member dictionaries with user info
        """
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            query = db.query(TeamMember, User).join(User).filter(
                TeamMember.team_id == team_id
            )

            if not include_inactive:
                query = query.filter(TeamMember.is_active == True)

            # Order: owner first, then admin, member, viewer
            from sqlalchemy import case
            role_order = case(
                (TeamMember.role == 'owner', 1),
                (TeamMember.role == 'admin', 2),
                (TeamMember.role == 'member', 3),
                (TeamMember.role == 'viewer', 4),
                else_=5
            )
            results = query.order_by(role_order).all()

            members = []
            for member, user in results:
                member_dict = member.to_dict()
                member_dict['username'] = user.username
                member_dict['email'] = user.email
                members.append(member_dict)

            return members

    def add_member(self, team_id: str, user_id: str, inviter_id: str,
                   role: str = 'member') -> Dict[str, Any]:
        """
        Add a member to the team.

        Args:
            team_id: Team ID
            user_id: User ID to add
            inviter_id: User ID adding the member (must have permissions)
            role: Role to assign (member, admin, viewer)

        Returns:
            Result dictionary
        """
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            # Check inviter permissions
            inviter = db.query(TeamMember).filter(
                TeamMember.team_id == team_id,
                TeamMember.user_id == inviter_id
            ).first()

            if not inviter or not inviter.can_manage_members:
                return {
                    'success': False,
                    'error': 'Insufficient permissions to add members'
                }

            # Check if user already a member
            existing = db.query(TeamMember).filter(
                TeamMember.team_id == team_id,
                TeamMember.user_id == user_id
            ).first()

            if existing:
                return {
                    'success': False,
                    'error': 'User is already a team member'
                }

            # Set permissions based on role
            permissions = self._get_role_permissions(role)

            # Create membership
            member = TeamMember(
                team_id=team_id,
                user_id=user_id,
                role=role,
                **permissions
            )

            db.add(member)

            # Update team member count
            team = db.query(Team).filter(Team.id == team_id).first()
            team.member_count += 1

            db.commit()
            db.refresh(member)

            return {
                'success': True,
                'member': member.to_dict()
            }

    def remove_member(self, team_id: str, user_id: str, remover_id: str) -> Dict[str, Any]:
        """
        Remove a member from the team.

        Args:
            team_id: Team ID
            user_id: User ID to remove
            remover_id: User ID removing the member (must have permissions)

        Returns:
            Result dictionary
        """
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            # Check remover permissions
            remover = db.query(TeamMember).filter(
                TeamMember.team_id == team_id,
                TeamMember.user_id == remover_id
            ).first()

            if not remover or not remover.can_manage_members:
                return {
                    'success': False,
                    'error': 'Insufficient permissions to remove members'
                }

            # Get member to remove
            member = db.query(TeamMember).filter(
                TeamMember.team_id == team_id,
                TeamMember.user_id == user_id
            ).first()

            if not member:
                return {
                    'success': False,
                    'error': 'Member not found'
                }

            # Cannot remove owner
            if member.role == 'owner':
                return {
                    'success': False,
                    'error': 'Cannot remove team owner'
                }

            db.delete(member)

            # Update team member count
            team = db.query(Team).filter(Team.id == team_id).first()
            team.member_count -= 1

            db.commit()

            return {
                'success': True,
                'message': 'Member removed successfully'
            }

    def update_member_role(self, team_id: str, user_id: str, new_role: str,
                          updater_id: str) -> Dict[str, Any]:
        """
        Update a member's role.

        Args:
            team_id: Team ID
            user_id: User ID to update
            new_role: New role (admin, member, viewer)
            updater_id: User ID making the update (must have permissions)

        Returns:
            Result dictionary
        """
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            # Check updater permissions
            updater = db.query(TeamMember).filter(
                TeamMember.team_id == team_id,
                TeamMember.user_id == updater_id
            ).first()

            if not updater or not updater.can_manage_members:
                return {
                    'success': False,
                    'error': 'Insufficient permissions to update roles'
                }

            # Get member to update
            member = db.query(TeamMember).filter(
                TeamMember.team_id == team_id,
                TeamMember.user_id == user_id
            ).first()

            if not member:
                return {
                    'success': False,
                    'error': 'Member not found'
                }

            # Cannot change owner role
            if member.role == 'owner' or new_role == 'owner':
                return {
                    'success': False,
                    'error': 'Cannot change owner role'
                }

            # Update role and permissions
            member.role = new_role
            permissions = self._get_role_permissions(new_role)
            for key, value in permissions.items():
                setattr(member, key, value)

            db.commit()
            db.refresh(member)

            return {
                'success': True,
                'member': member.to_dict()
            }

    def create_invitation(self, team_id: str, inviter_id: str,
                         email: Optional[str] = None,
                         user_id: Optional[str] = None,
                         role: str = 'member',
                         expires_in_days: int = 7) -> Dict[str, Any]:
        """
        Create a team invitation.

        Args:
            team_id: Team ID
            inviter_id: User ID creating the invitation
            email: Email to invite (for non-registered users)
            user_id: User ID to invite (for registered users)
            role: Role to assign when accepted
            expires_in_days: Days until invitation expires

        Returns:
            Result dictionary with invitation
        """
        if not email and not user_id:
            return {
                'success': False,
                'error': 'Either email or user_id must be provided'
            }

        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            # Check inviter permissions
            inviter = db.query(TeamMember).filter(
                TeamMember.team_id == team_id,
                TeamMember.user_id == inviter_id
            ).first()

            team = db.query(Team).filter(Team.id == team_id).first()

            # Check if inviter can invite (must be admin/owner OR team allows member invites)
            can_invite = (inviter and inviter.can_manage_members) or \
                        (inviter and team and team.allow_member_invites)

            if not can_invite:
                return {
                    'success': False,
                    'error': 'Insufficient permissions to send invitations'
                }

            # Generate unique token
            token = secrets.token_urlsafe(32)

            # Create invitation
            invitation = TeamInvitation(
                team_id=team_id,
                email=email,
                user_id=user_id,
                invited_by_id=inviter_id,
                role=role,
                token=token,
                expires_at=datetime.now(timezone.utc) + timedelta(days=expires_in_days)
            )

            db.add(invitation)
            db.commit()
            db.refresh(invitation)

            return {
                'success': True,
                'invitation': invitation.to_dict()
            }

    def accept_invitation(self, token: str, user_id: str) -> Dict[str, Any]:
        """
        Accept a team invitation.

        Args:
            token: Invitation token
            user_id: User ID accepting the invitation

        Returns:
            Result dictionary with membership
        """
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            invitation = db.query(TeamInvitation).filter(
                TeamInvitation.token == token,
                TeamInvitation.status == 'pending'
            ).first()

            if not invitation:
                return {
                    'success': False,
                    'error': 'Invalid or expired invitation'
                }

            # Check if invitation expired
            if invitation.expires_at < datetime.now(timezone.utc):
                invitation.status = 'expired'
                db.commit()
                return {
                    'success': False,
                    'error': 'Invitation has expired'
                }

            # Check if user matches invitation
            if invitation.user_id and invitation.user_id != user_id:
                return {
                    'success': False,
                    'error': 'This invitation is for a different user'
                }

            # Check if already a member
            existing = db.query(TeamMember).filter(
                TeamMember.team_id == invitation.team_id,
                TeamMember.user_id == user_id
            ).first()

            if existing:
                invitation.status = 'accepted'
                invitation.responded_at = datetime.now(timezone.utc)
                db.commit()
                return {
                    'success': False,
                    'error': 'You are already a member of this team'
                }

            # Create membership
            permissions = self._get_role_permissions(invitation.role)
            member = TeamMember(
                team_id=invitation.team_id,
                user_id=user_id,
                role=invitation.role,
                **permissions
            )

            db.add(member)

            # Update invitation status
            invitation.status = 'accepted'
            invitation.responded_at = datetime.now(timezone.utc)

            # Update team member count
            team = db.query(Team).filter(Team.id == invitation.team_id).first()
            team.member_count += 1

            db.commit()
            db.refresh(member)

            return {
                'success': True,
                'member': member.to_dict(),
                'team': team.to_dict()
            }

    def decline_invitation(self, token: str, user_id: str) -> Dict[str, Any]:
        """
        Decline a team invitation.

        Args:
            token: Invitation token
            user_id: User ID declining the invitation

        Returns:
            Result dictionary
        """
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            invitation = db.query(TeamInvitation).filter(
                TeamInvitation.token == token,
                TeamInvitation.status == 'pending'
            ).first()

            if not invitation:
                return {
                    'success': False,
                    'error': 'Invalid invitation'
                }

            # Check if user matches invitation
            if invitation.user_id and invitation.user_id != user_id:
                return {
                    'success': False,
                    'error': 'This invitation is for a different user'
                }

            invitation.status = 'declined'
            invitation.responded_at = datetime.now(timezone.utc)
            db.commit()

            return {
                'success': True,
                'message': 'Invitation declined'
            }

    def cancel_invitation(self, invitation_id: str, user_id: str) -> Dict[str, Any]:
        """
        Cancel a pending invitation.

        Args:
            invitation_id: Invitation ID
            user_id: User ID canceling (must have permissions)

        Returns:
            Result dictionary
        """
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            invitation = db.query(TeamInvitation).filter(
                TeamInvitation.id == invitation_id
            ).first()

            if not invitation:
                return {
                    'success': False,
                    'error': 'Invitation not found'
                }

            # Check permissions (must be inviter or team admin)
            is_inviter = invitation.invited_by_id == user_id

            member = db.query(TeamMember).filter(
                TeamMember.team_id == invitation.team_id,
                TeamMember.user_id == user_id
            ).first()

            is_admin = member and member.can_manage_members

            if not (is_inviter or is_admin):
                return {
                    'success': False,
                    'error': 'Insufficient permissions to cancel invitation'
                }

            db.delete(invitation)
            db.commit()

            return {
                'success': True,
                'message': 'Invitation canceled'
            }

    def get_team_invitations(self, team_id: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get team invitations.

        Args:
            team_id: Team ID
            status: Optional status filter (pending, accepted, declined)

        Returns:
            List of invitations
        """
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            query = db.query(TeamInvitation).filter(
                TeamInvitation.team_id == team_id
            )

            if status:
                query = query.filter(TeamInvitation.status == status)

            invitations = query.order_by(TeamInvitation.created_at.desc()).all()

            return [inv.to_dict() for inv in invitations]

    def get_user_teams(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Get all teams a user is a member of.

        Args:
            user_id: User ID

        Returns:
            List of teams with membership info
        """
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            results = db.query(Team, TeamMember).join(TeamMember).filter(
                TeamMember.user_id == user_id,
                TeamMember.is_active == True
            ).order_by(Team.name).all()

            teams = []
            for team, member in results:
                team_dict = team.to_dict()
                team_dict['role'] = member.role
                team_dict['permissions'] = member.to_dict()
                teams.append(team_dict)

            return teams

    def get_user_invitations(self, user_id: str, email: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get pending invitations for a user.

        Args:
            user_id: User ID
            email: Optional email to check

        Returns:
            List of pending invitations
        """
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            query = db.query(TeamInvitation, Team).join(Team).filter(
                TeamInvitation.status == 'pending',
                TeamInvitation.expires_at > datetime.now(timezone.utc)
            )

            # Filter by user_id or email
            if email:
                query = query.filter(
                    or_(
                        TeamInvitation.user_id == user_id,
                        TeamInvitation.email == email
                    )
                )
            else:
                query = query.filter(TeamInvitation.user_id == user_id)

            results = query.order_by(TeamInvitation.created_at.desc()).all()

            invitations = []
            for invitation, team in results:
                inv_dict = invitation.to_dict()
                inv_dict['team_name'] = team.name
                inv_dict['team_slug'] = team.slug
                invitations.append(inv_dict)

            return invitations

    def _get_role_permissions(self, role: str) -> Dict[str, bool]:
        """Get permissions for a role."""
        permissions = {
            'owner': {
                'can_manage_members': True,
                'can_manage_settings': True,
                'can_create_rules': True,
                'can_manage_plugins': True
            },
            'admin': {
                'can_manage_members': True,
                'can_manage_settings': True,
                'can_create_rules': True,
                'can_manage_plugins': True
            },
            'member': {
                'can_manage_members': False,
                'can_manage_settings': False,
                'can_create_rules': True,
                'can_manage_plugins': False
            },
            'viewer': {
                'can_manage_members': False,
                'can_manage_settings': False,
                'can_create_rules': False,
                'can_manage_plugins': False
            }
        }

        return permissions.get(role, permissions['member'])

    def check_permission(self, team_id: str, user_id: str, permission: str) -> bool:
        """
        Check if a user has a specific permission in a team.

        Args:
            team_id: Team ID
            user_id: User ID
            permission: Permission to check

        Returns:
            True if user has permission, False otherwise
        """
        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            member = db.query(TeamMember).filter(
                TeamMember.team_id == team_id,
                TeamMember.user_id == user_id,
                TeamMember.is_active == True
            ).first()

            if not member:
                return False

            return getattr(member, permission, False)
