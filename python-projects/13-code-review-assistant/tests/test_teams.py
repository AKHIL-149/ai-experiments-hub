"""
Teams, found by using the Teams page (which could only pick a team: there was no way to make one, invite
anyone, or put a repository in one).

  - nothing could attach a repository to a team, so the dashboard, analytics and activity were always empty,
    and every query behind them used columns that do not exist (Issue.repository_id, Review.repository_id,
    AnalysisJob.repository_id/created_at, Repository.description, TeamMember.created_at): they only
    "worked" for a team with no repositories
  - roles were not checked: a team admin (or any member, when member invites are on) could make an 'owner'
  - an invitation sent to an email address could be accepted or declined by anyone holding its token, and
    the token was listed for every member
  - a plain member could not leave a team; names, slugs and visibilities were not validated; member counts
    drifted; deleting a team left its repositories pointing at it
  - every page had its own header with its own links; the navigation is now one partial
"""

import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import server
from src.core.database import (
    AnalysisJob, CodeFile, DatabaseManager, Issue, IssueCategory, IssueSeverity, PullRequest, Repository,
    Review, ReviewComment, Team, TeamInvitation, TeamMember, User,
)
from tests.test_data_isolation import make_account, make_issue, _delete_user

ROOT = Path(__file__).resolve().parent.parent


def slug():
    return f'team-{uuid.uuid4().hex[:10]}'


@pytest.fixture
def accounts():
    """Accounts made by a test, deleted afterwards"""
    made = []

    def make(prefix='member'):
        client = make_account(prefix)
        made.append(client)
        return client

    yield make
    for client in made:
        _delete_user(client.account['id'])


@pytest.fixture
def owner(accounts):
    return accounts('owner')


def create_team(client, **fields):
    body = {'name': 'Platform', 'slug': slug(), **fields}
    response = client.post('/api/teams', json=body)
    assert response.status_code == 200, response.text
    return response.json()['team']['id']


def join(team_id, client, role='member'):
    """Make `client` a member directly, whatever the API allows"""
    with DatabaseManager().get_session() as db:
        db.add(TeamMember(
            team_id=team_id, user_id=client.account['id'], role=role,
            can_manage_members=role in ('owner', 'admin'), can_manage_settings=role in ('owner', 'admin'),
            can_create_rules=role != 'viewer', can_manage_plugins=role in ('owner', 'admin')))
        db.commit()


def members(client, team_id):
    return {m['user_id']: m for m in client.get(f'/api/teams/{team_id}/members').json()['members']}


def stored_count(team_id):
    with DatabaseManager().get_session() as db:
        return db.query(Team).get(team_id).member_count


class TestTeamFields:
    @pytest.mark.parametrize('fields,message', [
        ({'name': ''}, 'name is required'), ({'name': '   '}, 'name is required'),
        ({'name': 'x' * 101}, 'at most 100'), ({'slug': 'Has Space'}, 'Slug must be'),
        ({'slug': 'ab'}, 'Slug must be'), ({'slug': '-abc'}, 'Slug must be'), ({'slug': 'abc-'}, 'Slug must be'),
        ({'slug': 'a/b/c'}, 'Slug must be'), ({'slug': 'x' * 51}, 'Slug must be'), ({'slug': '<b>x</b>'}, 'Slug must be'),
        ({'visibility': 'banana'}, 'Visibility must be'), ({'description': 'x' * 2001}, 'at most 2000'),
    ])
    def test_a_new_team_is_checked(self, owner, fields, message):
        response = owner.post('/api/teams', json={'name': 'Platform', 'slug': slug(), **fields})
        assert response.status_code == 400 and message in response.json()['detail']

    def test_name_and_slug_are_tidied(self, owner):
        name = slug()
        team = owner.post('/api/teams', json={'name': '  Platform  ', 'slug': f'  {name.upper()}  '}).json()['team']
        assert team['name'] == 'Platform' and team['slug'] == name

    def test_a_slug_is_unique_whatever_its_case(self, owner):
        name = slug()
        assert owner.post('/api/teams', json={'name': 'A', 'slug': name}).status_code == 200
        again = owner.post('/api/teams', json={'name': 'B', 'slug': name.upper()})
        assert again.status_code == 400 and 'already exists' in again.json()['detail']

    def test_the_creator_is_the_owner(self, owner):
        team_id = create_team(owner)
        mine = members(owner, team_id)[owner.account['id']]
        assert mine['role'] == 'owner' and mine['can_manage_members'] and mine['can_manage_settings']
        assert stored_count(team_id) == 1

    @pytest.mark.parametrize('fields,message', [
        ({'name': ''}, 'name is required'), ({'visibility': 'x'}, 'Visibility must be'),
        ({'description': 5}, 'Description must be'), ({'allow_member_invites': 'yes'}, 'true or false'),
    ])
    def test_updates_are_checked(self, owner, fields, message):
        team_id = create_team(owner)
        response = owner.put(f'/api/teams/{team_id}', json=fields)
        assert response.status_code == 400 and message in response.json()['detail']

    def test_an_update_changes_only_the_allowed_fields(self, owner):
        team_id = create_team(owner)
        response = owner.put(f'/api/teams/{team_id}', json={
            'name': 'Renamed', 'description': 'Hello', 'visibility': 'public', 'allow_member_invites': True,
            'member_count': 99, 'plan': 'enterprise', 'slug': 'taken-over'})
        team = response.json()['team']
        assert (team['name'], team['description'], team['visibility'], team['allow_member_invites']) == (
            'Renamed', 'Hello', 'public', True)
        assert team['member_count'] == 1 and team['plan'] == 'free' and team['slug'] != 'taken-over'

    def test_only_those_who_manage_settings_update_the_team(self, owner, accounts):
        team_id = create_team(owner)
        member, viewer = accounts(), accounts()
        join(team_id, member, 'member')
        join(team_id, viewer, 'viewer')
        for client in (member, viewer):
            response = client.put(f'/api/teams/{team_id}', json={'name': 'Mine now'})
            assert response.status_code == 400 and 'Insufficient permissions' in response.json()['detail']
        assert owner.get(f'/api/teams/{team_id}').json()['name'] == 'Platform'

    def test_only_the_owner_deletes_the_team(self, owner, accounts):
        team_id = create_team(owner)
        admin = accounts()
        join(team_id, admin, 'admin')
        refused = admin.delete(f'/api/teams/{team_id}')
        assert refused.status_code == 400 and 'Only team owner' in refused.json()['detail']
        assert owner.delete(f'/api/teams/{team_id}').status_code == 200
        assert owner.get(f'/api/teams/{team_id}').status_code == 404

    def test_deleting_a_team_gives_its_repositories_back(self, owner):
        team_id = create_team(owner)
        with DatabaseManager().get_session() as db:
            repo = Repository(user_id=owner.account['id'], name='r', github_url='https://github.com/o/r', team_id=team_id)
            db.add(repo)
            db.commit()
            repo_id = repo.id
        owner.post('/api/teams/%s/invitations' % team_id, json={'email': 'someone@example.com'})
        assert owner.delete(f'/api/teams/{team_id}').status_code == 200
        with DatabaseManager().get_session() as db:
            assert db.query(Repository).get(repo_id).team_id is None
            assert db.query(TeamMember).filter_by(team_id=team_id).count() == 0
            assert db.query(TeamInvitation).filter_by(team_id=team_id).count() == 0

    def test_only_members_see_a_team(self, owner, accounts):
        team_id = create_team(owner)
        stranger = accounts()
        for path in ('', '/members', '/invitations', '/analytics', '/repositories', '/leaderboard', '/activity'):
            assert stranger.get(f'/api/teams/{team_id}{path}').status_code == 404, path
        assert stranger.get('/api/teams').json()['teams'] == []
        assert [t['id'] for t in owner.get('/api/teams').json()['teams']] == [team_id]


class TestRolesAndMembers:
    def add(self, client, team_id, target, role='member'):
        return client.post(f'/api/teams/{team_id}/members', json={'user_id': target.account['id'], 'role': role})

    def test_the_owner_adds_members_and_the_count_follows(self, owner, accounts):
        team_id = create_team(owner)
        one, two = accounts(), accounts()
        assert self.add(owner, team_id, one).status_code == 200
        assert self.add(owner, team_id, two, 'viewer').status_code == 200
        assert stored_count(team_id) == 3
        assert owner.delete(f"/api/teams/{team_id}/members/{one.account['id']}").status_code == 200
        assert stored_count(team_id) == 2

    @pytest.mark.parametrize('role', ['owner', 'superuser', '', 'ADMIN', None])
    def test_only_assignable_roles_can_be_given(self, owner, accounts, role):
        team_id = create_team(owner)
        target = accounts()
        response = self.add(owner, team_id, target, role)
        assert response.status_code == 400 and 'Role must be one of' in response.json()['detail']
        assert target.account['id'] not in members(owner, team_id)

    def test_an_unknown_or_inactive_user_cannot_be_added(self, owner, accounts):
        team_id = create_team(owner)
        assert owner.post(f'/api/teams/{team_id}/members', json={'user_id': 'nope', 'role': 'member'}).status_code == 400
        inactive = accounts()
        with DatabaseManager().get_session() as db:
            db.query(User).filter(User.id == inactive.account['id']).update({'is_active': False})
            db.commit()
        response = self.add(owner, team_id, inactive)
        assert response.status_code == 400 and 'User not found' in response.json()['detail']

    def test_a_member_twice_is_refused(self, owner, accounts):
        team_id = create_team(owner)
        target = accounts()
        assert self.add(owner, team_id, target).status_code == 200
        again = self.add(owner, team_id, target)
        assert again.status_code == 400 and 'already' in again.json()['detail']

    def test_an_admin_cannot_make_an_admin_or_an_owner(self, owner, accounts):
        team_id = create_team(owner)
        admin, target = accounts(), accounts()
        join(team_id, admin, 'admin')
        for role in ('admin', 'owner'):
            assert self.add(admin, team_id, target, role).status_code == 400
        assert self.add(admin, team_id, target, 'member').status_code == 200

    def test_only_the_owner_changes_admins(self, owner, accounts):
        team_id = create_team(owner)
        admin, other_admin, member = accounts(), accounts(), accounts()
        join(team_id, admin, 'admin')
        join(team_id, other_admin, 'admin')
        join(team_id, member, 'member')
        role_url = lambda user: f"/api/teams/{team_id}/members/{user.account['id']}/role"
        # an admin cannot promote a member, demote an admin or remove an admin
        assert admin.put(role_url(member), json={'role': 'admin'}).status_code == 400
        assert admin.put(role_url(other_admin), json={'role': 'viewer'}).status_code == 400
        removed = admin.delete(f"/api/teams/{team_id}/members/{other_admin.account['id']}")
        assert removed.status_code == 400 and 'owner can remove an admin' in removed.json()['detail']
        # but can change an ordinary member
        assert admin.put(role_url(member), json={'role': 'viewer'}).status_code == 200
        # the owner can do all of it
        assert owner.put(role_url(member), json={'role': 'admin'}).status_code == 200
        assert owner.put(role_url(other_admin), json={'role': 'member'}).status_code == 200
        assert owner.delete(f"/api/teams/{team_id}/members/{admin.account['id']}").status_code == 200

    @pytest.mark.parametrize('role', ['owner', 'god', ''])
    def test_a_role_change_is_checked(self, owner, accounts, role):
        team_id = create_team(owner)
        member = accounts()
        join(team_id, member, 'member')
        response = owner.put(f"/api/teams/{team_id}/members/{member.account['id']}/role", json={'role': role})
        assert response.status_code == 400
        assert members(owner, team_id)[member.account['id']]['role'] == 'member'

    def test_a_role_change_changes_what_the_member_may_do(self, owner, accounts):
        team_id = create_team(owner)
        member = accounts()
        join(team_id, member, 'member')
        assert not members(owner, team_id)[member.account['id']]['can_manage_members']
        owner.put(f"/api/teams/{team_id}/members/{member.account['id']}/role", json={'role': 'admin'})
        assert members(owner, team_id)[member.account['id']]['can_manage_members']
        owner.put(f"/api/teams/{team_id}/members/{member.account['id']}/role", json={'role': 'viewer'})
        got = members(owner, team_id)[member.account['id']]
        assert not got['can_manage_members'] and not got['can_create_rules']

    def test_the_owner_cannot_be_changed_removed_or_leave(self, owner, accounts):
        team_id = create_team(owner)
        admin = accounts()
        join(team_id, admin, 'admin')
        me = owner.account['id']
        assert admin.delete(f'/api/teams/{team_id}/members/{me}').status_code == 400
        assert admin.put(f'/api/teams/{team_id}/members/{me}/role', json={'role': 'member'}).status_code == 400
        left = owner.delete(f'/api/teams/{team_id}/members/{me}')
        assert left.status_code == 400 and 'owner' in left.json()['detail']
        assert members(owner, team_id)[me]['role'] == 'owner'

    @pytest.mark.parametrize('role', ['member', 'viewer', 'admin'])
    def test_anyone_but_the_owner_can_leave(self, owner, accounts, role):
        # a plain member had no permission to remove themselves
        team_id = create_team(owner)
        leaver = accounts()
        join(team_id, leaver, role)
        assert leaver.delete(f"/api/teams/{team_id}/members/{leaver.account['id']}").status_code == 200
        assert leaver.get(f'/api/teams/{team_id}').status_code == 404
        assert stored_count(team_id) == 1

    def test_a_member_cannot_remove_someone_else(self, owner, accounts):
        team_id = create_team(owner)
        one, two = accounts(), accounts()
        join(team_id, one, 'member')
        join(team_id, two, 'member')
        assert one.delete(f"/api/teams/{team_id}/members/{two.account['id']}").status_code == 400
        assert two.account['id'] in members(owner, team_id)

    def test_a_stranger_cannot_remove_anyone(self, owner, accounts):
        team_id = create_team(owner)
        member, stranger = accounts(), accounts()
        join(team_id, member, 'member')
        assert stranger.delete(f"/api/teams/{team_id}/members/{member.account['id']}").status_code == 400
        assert member.account['id'] in members(owner, team_id)


class TestInvitations:
    def invite(self, client, team_id, **body):
        return client.post(f'/api/teams/{team_id}/invitations', json=body)

    def test_by_username_with_a_token_for_the_inviter(self, owner, accounts):
        team_id = create_team(owner)
        guest = accounts()
        response = self.invite(owner, team_id, username=guest.account['username'].upper(), role='viewer')
        assert response.status_code == 200
        invitation = response.json()['invitation']
        assert invitation['user_id'] == guest.account['id'] and invitation['role'] == 'viewer' and invitation['token']

    def test_the_invitee_sees_it_and_accepts(self, owner, accounts):
        team_id = create_team(owner)
        guest = accounts()
        token = self.invite(owner, team_id, username=guest.account['username']).json()['invitation']['token']
        mine = guest.get('/api/me/invitations').json()['invitations']
        assert [i['team_id'] for i in mine] == [team_id] and mine[0]['team_name'] == 'Platform'
        accepted = guest.post(f'/api/invitations/{token}/accept')
        assert accepted.status_code == 200 and accepted.json()['member']['role'] == 'member'
        assert guest.account['id'] in members(owner, team_id) and stored_count(team_id) == 2
        assert guest.get('/api/me/invitations').json()['invitations'] == []
        # the token works once
        assert guest.post(f'/api/invitations/{token}/accept').status_code == 400

    def test_an_invitation_for_one_user_is_not_for_another(self, owner, accounts):
        team_id = create_team(owner)
        invited, other = accounts(), accounts()
        token = self.invite(owner, team_id, username=invited.account['username']).json()['invitation']['token']
        for action in ('accept', 'decline'):
            response = other.post(f'/api/invitations/{token}/{action}')
            assert response.status_code == 400 and 'different user' in response.json()['detail']
        assert other.account['id'] not in members(owner, team_id)

    def test_an_email_invitation_is_for_the_account_with_that_email(self, owner, accounts):
        team_id = create_team(owner)
        invited, thief = accounts(), accounts()
        email = invited.account['email'].upper()
        token = self.invite(owner, team_id, email=email, role='member').json()['invitation']['token']
        # anyone holding the token could take (or decline) it
        for action in ('accept', 'decline'):
            assert thief.post(f'/api/invitations/{token}/{action}').status_code == 400
        assert thief.account['id'] not in members(owner, team_id)
        assert [i['team_id'] for i in invited.get('/api/me/invitations').json()['invitations']] == [team_id]
        assert invited.post(f'/api/invitations/{token}/accept').status_code == 200
        assert invited.account['id'] in members(owner, team_id)

    def test_an_email_nobody_has_registered_yet_stays_pending(self, owner, accounts):
        team_id = create_team(owner)
        token = self.invite(owner, team_id, email='new.person@example.com').json()['invitation']['token']
        stranger = accounts()
        assert stranger.post(f'/api/invitations/{token}/accept').status_code == 400
        pending = owner.get(f'/api/teams/{team_id}/invitations?status=pending').json()['invitations']
        assert [i['email'] for i in pending] == ['new.person@example.com']

    def test_declining(self, owner, accounts):
        team_id = create_team(owner)
        guest = accounts()
        token = self.invite(owner, team_id, username=guest.account['username']).json()['invitation']['token']
        assert guest.post(f'/api/invitations/{token}/decline').status_code == 200
        assert guest.post(f'/api/invitations/{token}/accept').status_code == 400
        assert guest.get('/api/me/invitations').json()['invitations'] == []

    def test_an_expired_invitation_cannot_be_accepted(self, owner, accounts):
        team_id = create_team(owner)
        guest = accounts()
        token = self.invite(owner, team_id, username=guest.account['username']).json()['invitation']['token']
        with DatabaseManager().get_session() as db:
            db.query(TeamInvitation).filter_by(token=token).update(
                {'expires_at': datetime.now(timezone.utc) - timedelta(days=1)})
            db.commit()
        assert guest.get('/api/me/invitations').json()['invitations'] == []
        response = guest.post(f'/api/invitations/{token}/accept')
        assert response.status_code == 400 and 'expired' in response.json()['detail']

    def test_an_old_owner_invitation_gives_an_ordinary_member(self, owner, accounts):
        team_id = create_team(owner)
        guest = accounts()
        with DatabaseManager().get_session() as db:
            db.add(TeamInvitation(
                team_id=team_id, user_id=guest.account['id'], invited_by_id=owner.account['id'], role='owner',
                token='legacy-' + uuid.uuid4().hex, expires_at=datetime.now(timezone.utc) + timedelta(days=1)))
            db.commit()
            token = db.query(TeamInvitation).filter_by(team_id=team_id).first().token
        assert guest.post(f'/api/invitations/{token}/accept').json()['member']['role'] == 'member'

    @pytest.mark.parametrize('body,message', [
        ({'email': 'a@b.co', 'role': 'owner'}, 'Role must be one of'), ({'email': 'a@b.co', 'role': 'wizard'}, 'Role must be one of'),
        ({'email': 'nope'}, 'Invalid email'), ({'email': 'a b@c.co'}, 'Invalid email'),
        ({'email': 'a@b.co', 'expires_in_days': 0}, '1 to 30 days'), ({'email': 'a@b.co', 'expires_in_days': 365}, '1 to 30 days'),
        ({'email': 'a@b.co', 'expires_in_days': 'x'}, '1 to 30 days'), ({}, 'Either email or user_id'),
    ])
    def test_an_invitation_is_checked(self, owner, body, message):
        team_id = create_team(owner)
        response = self.invite(owner, team_id, **body)
        assert response.status_code == 400 and message in response.json()['detail']

    def test_an_unknown_username_is_a_404(self, owner):
        team_id = create_team(owner)
        assert self.invite(owner, team_id, username='nobody_by_that_name').status_code == 404

    def test_a_member_cannot_be_invited_again_nor_twice_at_once(self, owner, accounts):
        team_id = create_team(owner)
        member, guest = accounts(), accounts()
        join(team_id, member, 'member')
        again = self.invite(owner, team_id, username=member.account['username'])
        assert again.status_code == 400 and 'already a team member' in again.json()['detail']
        by_email = self.invite(owner, team_id, email=member.account['email'])
        assert by_email.status_code == 400
        assert self.invite(owner, team_id, username=guest.account['username']).status_code == 200
        twice = self.invite(owner, team_id, username=guest.account['username'])
        assert twice.status_code == 400 and 'pending invitation' in twice.json()['detail']
        assert self.invite(owner, team_id, email='x@example.com').status_code == 200
        assert self.invite(owner, team_id, email='X@Example.com').status_code == 400

    def test_there_is_a_limit_on_pending_invitations(self, owner, monkeypatch):
        from src.services import team_service
        monkeypatch.setattr(team_service, 'MAX_PENDING_INVITATIONS', 2)
        team_id = create_team(owner)
        for index in range(2):
            assert self.invite(owner, team_id, email=f'p{index}@example.com').status_code == 200
        full = self.invite(owner, team_id, email='p9@example.com')
        assert full.status_code == 400 and 'Too many pending' in full.json()['detail']

    def test_members_may_only_invite_when_the_team_allows_it(self, owner, accounts):
        team_id = create_team(owner)
        member = accounts()
        join(team_id, member, 'member')
        refused = self.invite(member, team_id, email='a@example.com')
        assert refused.status_code == 400 and 'Insufficient permissions' in refused.json()['detail']
        owner.put(f'/api/teams/{team_id}', json={'allow_member_invites': True})
        assert self.invite(member, team_id, email='a@example.com', role='viewer').status_code == 200

    @pytest.mark.parametrize('role', ['admin', 'owner'])
    def test_a_member_who_may_invite_cannot_hand_out_power(self, owner, accounts, role):
        # allow_member_invites let any member invite an owner
        team_id = create_team(owner)
        owner.put(f'/api/teams/{team_id}', json={'allow_member_invites': True})
        member = accounts()
        join(team_id, member, 'member')
        assert self.invite(member, team_id, email='a@example.com', role=role).status_code == 400

    def test_only_the_owner_invites_admins(self, owner, accounts):
        team_id = create_team(owner)
        admin = accounts()
        join(team_id, admin, 'admin')
        refused = self.invite(admin, team_id, email='a@example.com', role='admin')
        assert refused.status_code == 400 and 'owner can invite an admin' in refused.json()['detail']
        assert self.invite(owner, team_id, email='b@example.com', role='admin').status_code == 200

    def test_tokens_are_only_listed_to_those_who_manage_the_team(self, owner, accounts):
        team_id = create_team(owner)
        member, guest = accounts(), accounts()
        join(team_id, member, 'member')
        self.invite(owner, team_id, username=guest.account['username'])
        seen_by_owner = owner.get(f'/api/teams/{team_id}/invitations').json()['invitations'][0]
        seen_by_member = member.get(f'/api/teams/{team_id}/invitations').json()['invitations'][0]
        assert seen_by_owner['token'] and seen_by_owner['username'] == guest.account['username']
        assert 'token' not in seen_by_member and seen_by_member['username'] == guest.account['username']

    def test_cancelling(self, owner, accounts):
        team_id = create_team(owner)
        member, stranger = accounts(), accounts()
        join(team_id, member, 'member')
        invitation = self.invite(owner, team_id, email='a@example.com').json()['invitation']
        assert member.delete(f"/api/invitations/{invitation['id']}").status_code == 400
        assert stranger.delete(f"/api/invitations/{invitation['id']}").status_code == 400
        assert owner.delete(f"/api/invitations/{invitation['id']}").status_code == 200
        assert owner.get(f'/api/teams/{team_id}/invitations').json()['invitations'] == []


class TestSharingRepositories:
    @pytest.fixture
    def repo(self, owner):
        with DatabaseManager().get_session() as db:
            repository = Repository(user_id=owner.account['id'], name='mine', github_url='https://github.com/o/mine')
            db.add(repository)
            db.commit()
            return repository.id

    def share(self, client, team_id, repo_id):
        return client.post(f'/api/teams/{team_id}/repositories', json={'repository_id': repo_id})

    def test_share_and_stop_sharing(self, owner, repo):
        team_id = create_team(owner)
        assert owner.get('/api/repositories').json()['repositories'][0]['team_id'] is None
        assert self.share(owner, team_id, repo).status_code == 200
        assert owner.get('/api/repositories').json()['repositories'][0]['team_id'] == team_id
        assert [r['name'] for r in owner.get(f'/api/teams/{team_id}/repositories').json()['repositories']] == ['mine']
        assert owner.get('/api/teams').json()['teams'][0]['repository_count'] == 1
        assert owner.delete(f'/api/teams/{team_id}/repositories/{repo}').status_code == 200
        assert owner.get(f'/api/teams/{team_id}/repositories').json()['repositories'] == []
        assert owner.get('/api/teams').json()['teams'][0]['repository_count'] == 0

    def test_it_must_be_yours(self, owner, accounts, repo):
        team_id = create_team(owner)
        member = accounts()
        join(team_id, member, 'member')
        assert self.share(member, team_id, repo).status_code == 404
        assert self.share(owner, team_id, 'nope').status_code == 404

    def test_the_hidden_uploads_repository_cannot_be_shared(self, owner):
        team_id = create_team(owner)
        with DatabaseManager().get_session() as db:
            uploads = Repository(user_id=owner.account['id'], name='Uploaded Files', github_url='local://uploads')
            db.add(uploads)
            db.commit()
            uploads_id = uploads.id
        assert self.share(owner, team_id, uploads_id).status_code == 404

    def test_viewers_and_strangers_cannot_share(self, owner, accounts):
        team_id = create_team(owner)
        viewer, stranger = accounts(), accounts()
        join(team_id, viewer, 'viewer')
        with DatabaseManager().get_session() as db:
            ids = {}
            for client in (viewer, stranger):
                repository = Repository(user_id=client.account['id'], name='x', github_url='https://github.com/o/x')
                db.add(repository)
                db.commit()
                ids[client] = repository.id
        assert self.share(viewer, team_id, ids[viewer]).status_code == 403
        assert self.share(stranger, team_id, ids[stranger]).status_code == 404

    def test_a_repository_belongs_to_one_team(self, owner, repo):
        first, second = create_team(owner), create_team(owner)
        assert self.share(owner, first, repo).status_code == 200
        assert self.share(owner, first, repo).status_code == 409
        other = self.share(owner, second, repo)
        assert other.status_code == 409 and 'another team' in other.json()['detail']

    def test_who_may_stop_sharing(self, owner, accounts, repo):
        team_id = create_team(owner)
        member, admin = accounts(), accounts()
        join(team_id, member, 'member')
        join(team_id, admin, 'admin')
        self.share(owner, team_id, repo)
        assert member.delete(f'/api/teams/{team_id}/repositories/{repo}').status_code == 403   # not theirs
        assert admin.delete(f'/api/teams/{team_id}/repositories/{repo}').status_code == 200    # a manager may
        assert owner.delete(f'/api/teams/{team_id}/repositories/{repo}').status_code == 404    # already unshared

    def test_non_members_cannot_see_or_change_sharing(self, owner, accounts, repo):
        team_id = create_team(owner)
        stranger = accounts()
        assert self.share(stranger, team_id, repo).status_code == 404
        assert stranger.delete(f'/api/teams/{team_id}/repositories/{repo}').status_code == 404

    def test_sharing_does_not_open_the_repositorys_issues_to_the_team(self, owner, accounts, repo):
        team_id = create_team(owner)
        member = accounts()
        join(team_id, member, 'member')
        with DatabaseManager().get_session() as db:
            file_ = CodeFile(repository_id=repo, file_path='a.py', file_hash='h', language='python', lines_of_code=1)
            db.add(file_)
            db.commit()
            issue_id = make_issue(db, file_).id
        self.share(owner, team_id, repo)
        # the dashboard counts it, but the member's own Issues page and the issue itself stay private
        assert member.get(f'/api/teams/{team_id}/analytics').json()['total_issues'] == 1
        assert member.get('/api/issues').json()['total'] == 0
        assert member.get(f'/api/issues/{issue_id}').status_code == 404


@pytest.fixture
def team_data(owner, accounts):
    """A team with a shared repository (open, dismissed and resolved issues; a pull request with an issue, an
    analysis and a review with a comment), a member who has reviewed, and an unshared repository"""
    team_id = create_team(owner)
    reviewer = accounts('reviewer')
    join(team_id, reviewer, 'member')
    now = datetime.utcnow()
    with DatabaseManager().get_session() as db:
        repo = Repository(user_id=owner.account['id'], name='shared', github_url='https://github.com/o/shared', team_id=team_id)
        private = Repository(user_id=owner.account['id'], name='private', github_url='https://github.com/o/private')
        db.add_all([repo, private])
        db.commit()
        main = CodeFile(repository_id=repo.id, file_path='a.py', file_hash='1', language='python', lines_of_code=10)
        hidden = CodeFile(repository_id=private.id, file_path='b.py', file_hash='2', language='python', lines_of_code=10)
        pull_request = PullRequest(repository_id=repo.id, pr_number=1, title='PR', source_branch='f', target_branch='main')
        db.add_all([main, hidden, pull_request])
        db.commit()
        pr_file = CodeFile(pull_request_id=pull_request.id, file_path='c.py', file_hash='3', language='python', lines_of_code=5)
        db.add(pr_file)
        db.commit()

        make_issue(db, main, 'critical one', IssueSeverity.CRITICAL)
        make_issue(db, main, 'warning one', IssueSeverity.WARNING)
        make_issue(db, pr_file, 'pr warning', IssueSeverity.WARNING)
        gone = make_issue(db, main, 'dismissed', IssueSeverity.ERROR)
        fixed = make_issue(db, main, 'resolved', IssueSeverity.ERROR)
        gone.dismissed = True
        fixed.resolved = True
        make_issue(db, hidden, 'not in the team', IssueSeverity.CRITICAL)

        db.add(AnalysisJob(pull_request_id=pull_request.id, job_type='pr', started_at=now))
        review = Review(pull_request_id=pull_request.id, reviewer_id=reviewer.account['id'], approved=True)
        db.add(review)
        db.commit()
        db.add(ReviewComment(review_id=review.id, file_path='c.py', comment_text='nit'))
        db.commit()
        return SimpleNamespace(team=team_id, reviewer=reviewer, repo=repo.id)


class TestTeamAnalytics:
    def test_an_empty_team_has_zeros_not_errors(self, owner):
        team_id = create_team(owner)
        analytics = owner.get(f'/api/teams/{team_id}/analytics').json()
        assert analytics['total_repositories'] == 0 and analytics['total_issues'] == 0
        assert analytics['issues_by_severity'] == {'critical': 0, 'error': 0, 'warning': 0, 'info': 0}
        assert owner.get(f'/api/teams/{team_id}/repositories').json()['repositories'] == []
        assert owner.get(f'/api/teams/{team_id}/activity').json()['activity'] == []
        assert [r['username'] for r in owner.get(f'/api/teams/{team_id}/leaderboard').json()['leaderboard']] == [
            owner.account['username']]

    def test_analytics_count_open_issues_of_shared_repositories(self, owner, team_data):
        analytics = owner.get(f'/api/teams/{team_data.team}/analytics').json()
        # the dismissed and the resolved issue and the unshared repository's issue are not counted;
        # the pull request's issue is
        assert analytics['issues_by_severity'] == {'critical': 1, 'error': 0, 'warning': 2, 'info': 0}
        assert analytics['issues_by_category'] == {'security': 3}
        assert analytics['total_issues'] == 3 and analytics['total_repositories'] == 1

    def test_the_trends(self, owner, team_data):
        analytics = owner.get(f'/api/teams/{team_data.team}/analytics').json()
        # Rows are stored in UTC: the window was local time, which on a machine west of UTC left out
        # everything from the last few hours
        today = datetime.utcnow().date().isoformat()
        assert analytics['health_trend'] == [{'date': today, 'score': 94, 'issues': 3}]
        assert analytics['activity_trend'] == [{'date': today, 'analyses': 1}]

    def test_the_repositories_with_their_health(self, owner, team_data):
        repositories = owner.get(f'/api/teams/{team_data.team}/repositories').json()['repositories']
        assert [r['name'] for r in repositories] == ['shared']
        shared = repositories[0]
        assert shared['owner'] == owner.account['username'] and shared['status'] == 'pending'
        assert shared['total_issues'] == 3 and shared['severity_counts']['critical'] == 1
        assert isinstance(shared['health_score'], (int, float)) and shared['health_grade']
        assert 'description' not in shared

    def test_the_leaderboard_counts_what_happened_in_the_team(self, owner, team_data):
        rows = {r['username']: r for r in owner.get(f'/api/teams/{team_data.team}/leaderboard').json()['leaderboard']}
        reviewer = rows[team_data.reviewer.account['username']]
        assert (reviewer['reviews_count'], reviewer['comments_count'], reviewer['issues_found']) == (1, 1, 0)
        assert reviewer['contribution_score'] == 15
        mine = rows[owner.account['username']]
        assert mine['issues_found'] == 3 and mine['reviews_count'] == 0 and mine['contribution_score'] == 6
        ranked = owner.get(f'/api/teams/{team_data.team}/leaderboard').json()['leaderboard']
        assert [r['rank'] for r in ranked] == [1, 2] and ranked[0]['username'] == team_data.reviewer.account['username']

    def test_reviews_outside_the_team_do_not_count(self, owner, team_data):
        with DatabaseManager().get_session() as db:
            private = db.query(Repository).filter_by(name='private').first()
            pull_request = PullRequest(repository_id=private.id, pr_number=2, title='X', source_branch='f', target_branch='main')
            db.add(pull_request)
            db.commit()
            db.add(Review(pull_request_id=pull_request.id, reviewer_id=team_data.reviewer.account['id']))
            db.commit()
        rows = {r['username']: r for r in owner.get(f'/api/teams/{team_data.team}/leaderboard').json()['leaderboard']}
        assert rows[team_data.reviewer.account['username']]['reviews_count'] == 1

    def test_the_activity_feed(self, owner, team_data):
        feed = owner.get(f'/api/teams/{team_data.team}/activity').json()['activity']
        assert {item['type'] for item in feed} == {'analysis', 'review'}
        assert all(item['repository'] == 'shared' for item in feed)
        review = next(item for item in feed if item['type'] == 'review')
        assert team_data.reviewer.account['username'] in review['text'] and review['metadata']['approved'] is True
        timestamps = [item['timestamp'] for item in feed if item['timestamp']]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_the_feed_limit_is_bounded_and_respected(self, owner, team_data):
        assert len(owner.get(f'/api/teams/{team_data.team}/activity?limit=1').json()['activity']) == 1
        assert owner.get(f'/api/teams/{team_data.team}/activity?limit=0').status_code == 422
        assert owner.get(f'/api/teams/{team_data.team}/activity?limit=5000').status_code == 422

    def test_a_member_sees_the_same_numbers(self, owner, team_data):
        member = team_data.reviewer
        assert member.get(f'/api/teams/{team_data.team}/analytics').json()['total_issues'] == 3

    def test_stopping_sharing_removes_it_from_the_numbers(self, owner, team_data):
        owner.delete(f'/api/teams/{team_data.team}/repositories/{team_data.repo}')
        analytics = owner.get(f'/api/teams/{team_data.team}/analytics').json()
        assert analytics['total_repositories'] == 0 and analytics['total_issues'] == 0


NAV_TABS = ['/dashboard', '/analyze', '/repositories', '/pull-requests', '/issues', '/teams', '/schedules', '/notifications']
NAV_MORE = ['/rules/builder', '/plugins', '/settings/github-app', '/settings']
PAGES = [
    '/dashboard', '/analyze', '/repositories', '/repositories/new', '/pull-requests', '/pull-requests/import',
    '/issues', '/teams', '/schedules', '/notifications', '/notifications/preferences', '/settings',
    '/settings/github-app', '/plugins', '/rules/builder', '/demo/diff-viewer', '/demo/advanced-filters',
]


class TestNavigation:
    """Every page had its own header with its own links (Settings, Schedules and Analyze were missing
    from some, Plugins and the Rule builder from all): one partial now"""

    @pytest.mark.parametrize('path', PAGES)
    def test_every_page_has_the_same_navigation(self, owner, path):
        html = owner.get(path).text
        assert 'class="app-nav"' in html and '/static/css/nav.css' in html, path
        nav = html.split('class="app-nav"', 1)[1].split('</script>', 1)[0]
        for href in NAV_TABS + NAV_MORE:
            assert f'href="{href}"' in nav, (path, href)
        assert owner.account['username'] in nav and 'href="/logout"' in nav

    @pytest.mark.parametrize('path,active', [
        ('/dashboard', '/dashboard'), ('/analyze', '/analyze'), ('/repositories', '/repositories'),
        ('/repositories/new', '/repositories'), ('/pull-requests', '/pull-requests'), ('/issues', '/issues'),
        ('/teams', '/teams'), ('/schedules', '/schedules'), ('/notifications', '/notifications'),
    ])
    def test_the_current_page_is_highlighted_once(self, owner, path, active):
        nav = owner.get(path).text.split('class="app-nav"', 1)[1].split('</script>', 1)[0]
        current = re.findall(r'<a class="app-nav__link is-active" href="([^"]+)" aria-current="page"', nav)
        assert current == [active]

    @pytest.mark.parametrize('path', ['/rules/builder', '/plugins', '/settings', '/settings/github-app'])
    def test_pages_in_the_more_menu_highlight_it(self, owner, path):
        nav = owner.get(path).text.split('class="app-nav"', 1)[1].split('</script>', 1)[0]
        assert 'app-nav__more is-active' in nav and f'is-active" href="{path}"' in nav

    def test_a_signed_out_visitor_sees_login_and_register_only(self):
        html = TestClient(server.app).get('/login').text
        nav = html.split('class="app-nav"', 1)[1].split('</script>', 1)[0]
        assert 'href="/login"' in nav and 'href="/register"' in nav and 'href="/teams"' not in nav

    def test_the_old_per_page_headers_are_gone(self):
        for name in ('team_dashboard', 'schedules'):
            html = (ROOT / 'templates' / f'{name}.html').read_text()
            assert html.startswith('{% extends "base.html" %}') and '<nav' not in html
        for name in ('settings', 'plugins', 'github-app', 'issue_detail', 'diff_viewer_demo', 'advanced_filters_demo'):
            assert '{% include "_nav.html" %}' in (ROOT / 'templates' / f'{name}.html').read_text(), name

    def test_the_navbar_styles_live_in_one_place(self):
        style = (ROOT / 'static' / 'css' / 'style.css').read_text()
        assert '.navbar' not in style and '.nav-menu' not in style
        assert '.app-nav' in (ROOT / 'static' / 'css' / 'nav.css').read_text()


class TestTeamsPage:
    def test_the_page_renders_for_an_account(self, owner):
        page = owner.get('/teams')
        assert page.status_code == 200
        for element in ('id="current-team"', 'id="new-team-btn"', 'id="new-team-modal"', 'id="invite-form"',
                        'id="share-repo-select"', 'data-tab="members"', 'data-tab="leaderboard"'):
            assert element in page.text, element
        assert owner.account['username'] in page.text

    def test_signed_out_goes_to_login(self):
        response = TestClient(server.app).get('/teams', follow_redirects=False)
        assert response.status_code in (302, 307) and response.headers['location'] == '/login'

    def test_the_script_does_not_leak_globals_that_clash_with_app_js(self):
        # app.js declares `api` and `formatDate`: declaring them again was a SyntaxError that stopped the page
        script = (ROOT / 'static' / 'js' / 'team-dashboard.js').read_text()
        app_js = (ROOT / 'static' / 'js' / 'app.js').read_text()
        assert re.search(r'^(const|let|var|function|async function) +api\b', app_js, re.M)
        # everything is declared inside one function: the names it uses cannot clash with app.js's
        assert script.index('(() => {') < script.index('function formatDate') < script.rindex('})();')
        assert script.rstrip().endswith('})();')

    def test_everything_from_the_server_is_escaped(self):
        script = (ROOT / 'static' / 'js' / 'team-dashboard.js').read_text()
        for field in ('team.name', 'member.username', 'repo.name', 'invitation.team_name', 'row.username', 'item.text'):
            assert f'escapeHtml({field})' in script, field
        assert 'innerHTML' in script
        # and no value of those objects is put into the page raw anywhere (one escaped use elsewhere must not hide it)
        # (confirm() text and request URLs are not HTML)
        html_lines = [line for line in script.split('\n') if 'confirm(' not in line and "api('" not in line]
        raw = re.findall(r'\$\{(?:member|repo|team|invitation|row|item)\.[a-z_]+\}', '\n'.join(html_lines))
        assert raw == [], raw
