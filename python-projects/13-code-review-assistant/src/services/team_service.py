"""
Team Management Service - Create and manage teams, members, and invitations
"""

import re
import secrets
import uuid
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone, timedelta
from sqlalchemy import and_, func, or_

from src.core.database import (
    DatabaseManager, Team, TeamMember, TeamInvitation,
    User, CustomRule, Plugin, Repository
)


# Roles that can be given to a member or invitee. 'owner' is only ever the creator: the role was not
# checked, so a team admin (or, with member invites on, any member) could make an owner, who can delete
# the team. Only the owner grants or takes away 'admin'.
ASSIGNABLE_ROLES = ('admin', 'member', 'viewer')
ROLES_ANYONE_MAY_INVITE = ('member', 'viewer')
VISIBILITIES = ('private', 'public')
SLUG_PATTERN = re.compile(r'[a-z0-9][a-z0-9-]{1,48}[a-z0-9]')
EMAIL_PATTERN = re.compile(r'[^@\s<>"\']+@[^@\s<>"\']+\.[^@\s<>"\']+')
MAX_PENDING_INVITATIONS = 50


def _error(message: str) -> Dict[str, Any]:
    return {'success': False, 'error': message}


def validate_team_fields(fields: Dict[str, Any], creating: bool = False) -> Dict[str, Any]:
    """
    Check the fields of a team (those present in `fields`) and return the cleaned values.
    Raises ValueError with the reason. Any text was stored: an empty name, a slug with spaces or
    slashes, a visibility of 'banana'.
    """
    cleaned = dict(fields)
    if creating or 'name' in fields:
        name = fields.get('name')
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Team name is required")
        if len(name.strip()) > 100:
            raise ValueError("Team name must be at most 100 characters")
        cleaned['name'] = name.strip()
    if creating or 'slug' in fields:
        slug = fields.get('slug')
        if not isinstance(slug, str) or not SLUG_PATTERN.fullmatch(slug.strip().lower()):
            raise ValueError("Slug must be 3-50 characters: lowercase letters, numbers and dashes, "
                             "starting and ending with a letter or number")
        cleaned['slug'] = slug.strip().lower()
    if 'description' in fields and fields['description'] is not None:
        description = fields['description']
        if not isinstance(description, str) or len(description) > 2000:
            raise ValueError("Description must be text of at most 2000 characters")
        cleaned['description'] = description.strip()
    if 'visibility' in fields and fields['visibility'] not in VISIBILITIES:
        raise ValueError(f"Visibility must be one of: {', '.join(VISIBILITIES)}")
    if 'allow_member_invites' in fields and not isinstance(fields['allow_member_invites'], bool):
        raise ValueError("allow_member_invites must be true or false")
    return cleaned


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
        try:
            cleaned = validate_team_fields(
                {'name': name, 'slug': slug, 'description': description, 'visibility': visibility},
                creating=True)
        except ValueError as e:
            return _error(str(e))
        name, slug, description = cleaned['name'], cleaned['slug'], cleaned.get('description')

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
            try:
                kwargs = validate_team_fields({k: v for k, v in kwargs.items() if k in allowed_fields})
            except ValueError as e:
                return _error(str(e))
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

            # Repositories, rules and plugins that were shared with the team go back to their owners
            from src.core.database import Base
            for table in Base.metadata.sorted_tables:
                if 'team_id' in table.c and table.name not in ('teams', 'team_members', 'team_invitations'):
                    db.execute(table.update().where(table.c.team_id == team_id).values(team_id=None))

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

            if role not in ASSIGNABLE_ROLES:
                return _error(f"Role must be one of: {', '.join(ASSIGNABLE_ROLES)}")
            if role == 'admin' and inviter.role != 'owner':
                return _error('Only the team owner can make someone an admin')

            target = db.query(User).filter(User.id == user_id, User.is_active == True).first()
            if not target:
                return _error('User not found')

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
            db.flush()
            self._refresh_member_count(db, team_id)

            db.commit()
            db.refresh(member)

            return {
                'success': True,
                'member': member.to_dict()
            }

    @staticmethod
    def _refresh_member_count(db, team_id: str) -> None:
        """The stored count is counted, not nudged up and down by every code path"""
        from sqlalchemy import func
        team = db.query(Team).filter(Team.id == team_id).first()
        if team:
            team.member_count = db.query(func.count(TeamMember.id)).filter(
                TeamMember.team_id == team_id, TeamMember.is_active == True).scalar() or 0

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
            # Check remover permissions (anyone may remove themselves: a plain member could not leave)
            remover = db.query(TeamMember).filter(
                TeamMember.team_id == team_id,
                TeamMember.user_id == remover_id
            ).first()

            leaving = user_id == remover_id
            if not remover or not (leaving or remover.can_manage_members):
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
                    'error': 'The team owner cannot be removed or leave: delete the team instead'
                }

            if member.role == 'admin' and not leaving and remover.role != 'owner':
                return _error('Only the team owner can remove an admin')

            db.delete(member)
            db.flush()
            self._refresh_member_count(db, team_id)

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

            if new_role not in ASSIGNABLE_ROLES:
                return _error(f"Role must be one of: {', '.join(ASSIGNABLE_ROLES)}")
            if (new_role == 'admin' or member.role == 'admin') and updater.role != 'owner':
                return _error('Only the team owner can make or change an admin')

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

        if role not in ASSIGNABLE_ROLES:
            return _error(f"Role must be one of: {', '.join(ASSIGNABLE_ROLES)}")
        if not isinstance(expires_in_days, int) or isinstance(expires_in_days, bool) or not 1 <= expires_in_days <= 30:
            return _error('Invitations last from 1 to 30 days')
        if email is not None:
            email = email.strip().lower() if isinstance(email, str) else ''
            if len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
                return _error('Invalid email address')

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

            # Someone who may invite only because the team allows it cannot hand out power
            if not inviter.can_manage_members and role not in ROLES_ANYONE_MAY_INVITE:
                return _error(f"Members can only invite as: {', '.join(ROLES_ANYONE_MAY_INVITE)}")
            if role == 'admin' and inviter.role != 'owner':
                return _error('Only the team owner can invite an admin')

            invitee = None
            if user_id:
                invitee = db.query(User).filter(User.id == user_id, User.is_active == True).first()
                if not invitee:
                    return _error('User not found')
            elif email:
                invitee = db.query(User).filter(func.lower(User.email) == email).first()

            if invitee and db.query(TeamMember.id).filter(
                    TeamMember.team_id == team_id, TeamMember.user_id == invitee.id).first():
                return _error('That person is already a team member')

            now = datetime.now(timezone.utc)
            pending = db.query(TeamInvitation).filter(
                TeamInvitation.team_id == team_id, TeamInvitation.status == 'pending',
                TeamInvitation.expires_at > now)
            if pending.count() >= MAX_PENDING_INVITATIONS:
                return _error('Too many pending invitations: cancel some first')
            if invitee and pending.filter(TeamInvitation.user_id == invitee.id).first():
                return _error('That person already has a pending invitation')
            if email and pending.filter(func.lower(TeamInvitation.email) == email).first():
                return _error('That email already has a pending invitation')

            # Generate unique token
            token = secrets.token_urlsafe(32)

            # Create invitation
            invitation = TeamInvitation(
                team_id=team_id,
                email=email,
                user_id=user_id or (invitee.id if invitee else None),
                invited_by_id=inviter_id,
                role=role,
                token=token,
                expires_at=now + timedelta(days=expires_in_days)
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
            # SQLite gives back a naive datetime (stored as UTC): comparing it with an aware one raised
            # TypeError, so accepting an invitation always failed with a 500
            expires_at = invitation.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < datetime.now(timezone.utc):
                invitation.status = 'expired'
                db.commit()
                return {
                    'success': False,
                    'error': 'Invitation has expired'
                }

            # Check if user matches invitation
            if not self._invitation_is_for(db, invitation, user_id):
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

            # Create membership (an invitation stored with a role that is no longer assignable, such as
            # 'owner', gives an ordinary member)
            role = invitation.role if invitation.role in ASSIGNABLE_ROLES else 'member'
            permissions = self._get_role_permissions(role)
            member = TeamMember(
                team_id=invitation.team_id,
                user_id=user_id,
                role=role,
                **permissions
            )

            db.add(member)

            # Update invitation status
            invitation.status = 'accepted'
            invitation.responded_at = datetime.now(timezone.utc)

            db.flush()
            self._refresh_member_count(db, invitation.team_id)
            team = db.query(Team).filter(Team.id == invitation.team_id).first()

            db.commit()
            db.refresh(member)

            return {
                'success': True,
                'member': member.to_dict(),
                'team': team.to_dict()
            }

    @staticmethod
    def _invitation_is_for(db, invitation, user_id: str) -> bool:
        """
        An invitation to a user id is for that user. One sent to an email address is for the account
        with that email: it used to be for anyone who held the token, and the token was listed for every
        team member, so any account could take (or decline) an invitation meant for someone else.
        """
        if invitation.user_id:
            return invitation.user_id == user_id
        if invitation.email:
            user = db.query(User).filter(User.id == user_id).first()
            return bool(user and user.email and user.email.strip().lower() == invitation.email.strip().lower())
        return False

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
            if not self._invitation_is_for(db, invitation, user_id):
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

    def get_team_invitations(self, team_id: str, status: Optional[str] = None,
                             include_tokens: bool = False) -> List[Dict[str, Any]]:
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

            # The token is the key to the invitation: only those who manage the team see it
            names = {}
            wanted = [inv.user_id for inv in invitations if inv.user_id]
            if wanted:
                names = {u.id: u.username for u in db.query(User.id, User.username).filter(User.id.in_(wanted))}

            result = []
            for inv in invitations:
                data = inv.to_dict()
                data['username'] = names.get(inv.user_id)
                if not include_tokens:
                    data.pop('token', None)
                result.append(data)
            return result

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
                        func.lower(TeamInvitation.email) == email.strip().lower()
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
