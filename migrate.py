#!/usr/bin/env python3
#
# imports projects, users, groups, issues, labels, milestones, keys
# and collaborators from Gitlab to Forgejo
#
"""
Usage: migrate.py [--users] [--groups] [--projects] [--all] [--notify]
       migrate.py --help

Migration script to import projects, users, groups, from Gitlab to Forgejo.

Options
  -h --help   Show this screen
  --users     migrate users
  --groups    migrate groups
  --projects  migrate projects
  --all       migrate all
  --notify    send notification to users
"""
import os
import json
import re
import random
import string
import configparser
from typing import Dict
from typing import List

from docopt import docopt
import requests
import dateutil.parser

import gitlab  # pip install python-gitlab
import gitlab.v4.objects
import pyforgejo  # pip install pyforgejo (https://github.com/h44z/pyforgejo)

# Forgejo API imports: I started using the pyforgejo library, but I swapped to requests
# as it is much easier to use and the pyforgejo library is not yet fully implemented.
# So it is still partially used in the code.
from pyforgejo import AuthenticatedClient
from pyforgejo.api.miscellaneous import get_version
from pyforgejo.api.user import user_get
from pyforgejo.api.user import user_list_keys
from pyforgejo.api.admin import admin_create_user
from pyforgejo.models.create_user_option import CreateUserOption
from pyforgejo.api.admin import admin_create_public_key
from pyforgejo.models.create_key_option import CreateKeyOption
from pyforgejo.api.organization import org_get
from pyforgejo.api.organization import org_list_teams
from pyforgejo.api.organization import org_create
from pyforgejo.models.create_org_option import CreateOrgOption
from pyforgejo.api.repository import repo_get
from pyforgejo.api.repository import repo_migrate
from pyforgejo.models.migrate_repo_options import MigrateRepoOptions


SCRIPT_VERSION = "0.5"
GLOBAL_ERROR_COUNT = 0

#######################
# CONFIG SECTION START
#######################
if not os.path.exists(".migrate.ini"):
    print("Please create a .migrate.ini file using the config template from the README!")
    exit()

config = configparser.RawConfigParser()
config.read(".migrate.ini")
GITLAB_URL = config.get("migrate", "gitlab_url")
GITLAB_TOKEN = config.get("migrate", "gitlab_token")
GITLAB_ADMIN_USER = config.get("migrate", "gitlab_admin_user")
GITLAB_ADMIN_PASS = config.get("migrate", "gitlab_admin_pass")
FORGEJO_URL = config.get("migrate", "forgejo_url")
FORGEJO_API_URL = f"{FORGEJO_URL}/api/v1"
FORGEJO_TOKEN = config.get("migrate", "forgejo_token")
#######################
# CONFIG SECTION END
#######################


def main():
    """Main function"""
    _args = docopt(__doc__)
    args = {k.replace("--", ""): v for k, v in _args.items()}

    print_color(Bcolors.HEADER, "---=== Gitlab to Forgejo migration ===---")
    print(f"Version: {SCRIPT_VERSION}")
    print()

    # private token or personal token authentication
    gl = gitlab.Gitlab(GITLAB_URL, private_token=GITLAB_TOKEN)
    gl.auth()
    assert isinstance(gl.user, gitlab.v4.objects.CurrentUser)
    print_info(f"Connected to Gitlab, version: {gl.version()[0]}")

    fg = AuthenticatedClient(base_url=FORGEJO_API_URL, token=FORGEJO_TOKEN)
    fg_ver = json.loads(get_version.sync_detailed(client=fg).content)["version"]
    print_info(f"Connected to Forgejo, version: {fg_ver}")

    # IMPORT USERS
    if args["users"] or args["all"]:
        import_users(gl, fg)
    # IMPORT GROUPS
    if args["groups"] or args["all"]:
        import_groups(gl, fg)
    # IMPORT PROJECTS
    if args["projects"] or args["all"]:
        import_projects(gl, fg)
    # IMPORT NOTHING ?
    if (
        not args["users"]
        and not args["groups"]
        and not args["projects"]
        and not args["all"]
    ):
        print()
        print_warning("No migration option(s) selected, nothing to do!")
        exit()

    print()
    if GLOBAL_ERROR_COUNT == 0:
        print_success("Migration finished with no errors!")
    else:
        print_error(f"Migration finished with {GLOBAL_ERROR_COUNT} errors!")


#
# Data loading helpers for Forgejo
#


def get_labels(fg_api: pyforgejo, owner: string, repo: string) -> List:
    """get labels for a repository"""
    existing_labels = []
    label_response: requests.Response = fg_api.get(f"/repos/{owner}/{repo}/labels")
    if label_response.ok:
        existing_labels = label_response.json()
    else:
        print_error(
            f"Failed to load existing milestones for project {repo}! {label_response.text}"
        )

    return existing_labels


def get_milestones(fg_api: pyforgejo, owner: string, repo: string) -> List:
    """get milestones for a repository"""
    existing_milestones = []
    milestone_response: requests.Response = fg_api.get(
        f"/repos/{owner}/{repo}/milestones"
    )
    if milestone_response.ok:
        existing_milestones = milestone_response.json()
    else:
        print_error(
            f"Failed to load existing milestones for project {repo}! {milestone_response.text}"
        )

    return existing_milestones


def get_issues(fg_api: pyforgejo, owner: string, repo: string) -> List:
    """get issues for a repository"""
    existing_issues = []
    issue_response: requests.Response = fg_api.get(
        f"/repos/{owner}/{repo}/issues", params={"state": "all", "page": -1}
    )
    if issue_response.ok:
        existing_issues = issue_response.json()
    else:
        print_error(
            f"Failed to load existing issues for project {repo}! {issue_response.text}"
        )

    return existing_issues


def get_teams(fg_api: pyforgejo, orgname: string) -> List:
    """get teams for an organization"""
    team_response: requests.Response = org_list_teams.sync_detailed(
        orgname, client=fg_api
    )
    if team_response.status_code.name == "OK":
        return json.loads(team_response.content)

    msg = json.loads(team_response.content)["errors"]
    print_error(f"Failed to load existing teams for organization {orgname}! {msg}")
    return []


def get_team_members(teamid: int) -> List:
    """get members for a team"""
    existing_members = []
    member_response: requests.Response = requests.get(
        f"{FORGEJO_API_URL}/teams/{teamid}/members",
        headers={"Authorization": FORGEJO_TOKEN},
        timeout=10,
    )
    if member_response.ok:
        existing_members = member_response.json()
    else:
        print_error(
            f"Failed to load existing members for team {teamid}! {member_response.text}"
        )

    return existing_members


def get_collaborators(fg_api: pyforgejo, owner: string, repo: string) -> List:
    """get collaborators for a repository"""
    existing_collaborators = []
    collaborator_response: requests.Response = fg_api.get(
        f"/repos/{owner}/{repo}/collaborators"
    )
    if collaborator_response.ok:
        existing_collaborators = collaborator_response.json()
    else:
        print_error(
            f"Failed to load existing collaborators for repo {repo}! {collaborator_response.text}"
        )

    return existing_collaborators


def get_user_or_group(project: gitlab.v4.objects.Project) -> Dict:
    """get user or group by name"""
    result = None
    proj_namespace_path = project.namespace["path"]
    proj_namespace_name = name_clean(project.namespace["name"])
    session = requests.Session()
    response: requests.Response = session.get(
        f"{FORGEJO_API_URL}/users/{proj_namespace_path}",
        headers={"Authorization": FORGEJO_TOKEN},
        timeout=10,
    )
    if response.ok:
        result = response.json()
    else:
        response: requests.Response = session.get(
            f"{FORGEJO_API_URL}/orgs/{proj_namespace_name}",
            headers={"Authorization": FORGEJO_TOKEN},
            timeout=10,
        )
        if response.ok:
            result = response.json()
        else:
            print_error(
                f"Failed to load user or group {proj_namespace_name}! {response.text}"
            )

    return result


def get_user_keys(fg_api: pyforgejo, username: string) -> Dict:
    """get public keys for a user"""
    key_response: requests.Response = user_list_keys.sync_detailed(
        username, client=fg_api
    )
    if key_response.status_code.name == "OK":
        return json.loads(key_response.content)

    status_code = key_response.status_code.name
    print_error(f"Failed to load user keys for user {username}! {status_code}")
    return []


def user_exists(fg_api: pyforgejo, username: string) -> bool:
    """check if a user exists"""
    user_response: requests.Response = user_get.sync_detailed(username, client=fg_api)
    if user_response.status_code.name == "OK":
        print_warning(f"User {username} already exists in Forgejo, skipping!")
        return True

    print(f"User {username} not found in Forgejo, importing!")
    return False


def user_key_exists(fg_api: pyforgejo, username: string, keyname: string) -> bool:
    """check if a public key exists for a user"""
    existing_keys = get_user_keys(fg_api, username)
    if existing_keys:
        existing_key = next(
            (item for item in existing_keys if item["title"] == keyname), None
        )

        if existing_key is not None:
            print_warning(
                f"Public key {keyname} already exists for user {username}, skipping!"
            )
            return True

        print(f"Public key {keyname} does not exist for user {username}, importing!")
        return False

    print(f"No public keys for user {username}, importing!")
    return False


def organization_exists(fg_api: pyforgejo, orgname: string) -> bool:
    """check if an organization exists"""
    group_response: requests.Response = org_get.sync_detailed(orgname, client=fg_api)
    if group_response.status_code.name == "OK":
        print_warning(f"Group {orgname} already exists in Forgejo, skipping!")
        return True

    print(f"Group {orgname} not found in Forgejo, importing!")
    return False


def member_exists(username: string, teamid: int) -> bool:
    """check if a member exists in a team"""
    existing_members = get_team_members(teamid)
    if existing_members:
        existing_member = next(
            (item for item in existing_members if item["username"] == username), None
        )

        if existing_member:
            print_warning(f"Member {username} is already in team {teamid}, skipping!")
            return True

        print(f"Member {username} is not in team {teamid}, importing!")
        return False

    print(f"No members in team {teamid}, importing!")
    return False


def collaborator_exists(
    fg_api: pyforgejo, _owner: string, repo: string, username: string
) -> bool:
    """check if a collaborator exists in a repository"""
    collaborator_response: requests.Response = fg_api.get(
        f"/repos/{repo}/collaborators/{username}"
    )
    if collaborator_response.ok:
        print_warning(f"Collaborator {username} already exists in Forgejo, skipping!")
    else:
        print(f"Collaborator {username} not found in Forgejo, importing!")

    return collaborator_response.ok


def repo_exists(fg_api: pyforgejo, owner: string, repo: string) -> bool:
    """check if a repository exists"""
    repo_response: requests.Response = repo_get.sync_detailed(
        owner=owner, repo=repo, client=fg_api
    )
    if repo_response.status_code.name == "OK":
        print_warning(f"Project {repo} already exists in Forgejo, skipping!")
        return True

    print(f"Project {repo} not found in Forgejo, importing!")
    return False


def label_exists(
    fg_api: pyforgejo, owner: string, repo: string, labelname: string
) -> bool:
    """check if a label exists in a repository"""
    existing_labels = get_labels(fg_api, owner, repo)
    if existing_labels:
        existing_label = next(
            (item for item in existing_labels if item["name"] == labelname), None
        )

        if existing_label is not None:
            print_warning(
                f"Label {labelname} already exists in project {repo}, skipping!"
            )
            return True

        print(f"Label {labelname} does not exist in project {repo}, importing!")
        return False

    print(f"No labels in project {repo}, importing!")
    return False


def milestone_exists(
    fg_api: pyforgejo, owner: string, repo: string, milestone: string
) -> bool:
    """check if a milestone exists in a repository"""
    existing_milestones = get_milestones(fg_api, owner, repo)
    if existing_milestones:
        existing_milestone = next(
            (item for item in existing_milestones if item["title"] == milestone), None
        )

        if existing_milestone is not None:
            print_warning(
                f"Milestone {milestone} already exists in project {repo}, skipping!"
            )
            return True

        print(f"Milestone {milestone} does not exist in project {repo}, importing!")
        return False

    print(f"No milestones in project {repo}, importing!")
    return False


def issue_exists(fg_api: pyforgejo, owner: string, repo: string, issue: string) -> bool:
    """check if an issue exists in a repository"""
    existing_issues = get_issues(fg_api, owner, repo)
    if existing_issues:
        existing_issue = next(
            (item for item in existing_issues if item["title"] == issue), None
        )

        if existing_issue is not None:
            print_warning(f"Issue {issue} already exists in project {repo}, skipping!")
            return True

        print(f"Issue {issue} does not exist in project {repo}, importing!")
        return False

    print(f"No issues in project {repo}, importing!")
    return False


#
# Import helper functions
#


def _import_project_labels(
    fg_api: pyforgejo,
    labels: List[gitlab.v4.objects.ProjectLabel],
    owner: string,
    repo: string,
):
    """import labels for a repository"""
    for label in labels:
        if not label_exists(fg_api, owner, repo, label.name):
            import_response: requests.Response = fg_api.post(
                f"/repos/{owner}/{repo}/labels",
                json={
                    "name": label.name,
                    "color": label.color,
                    "description": label.description,  # currently not supported
                },
            )
            if import_response.ok:
                print_info(f"Label {label.name} imported!")
            else:
                print_error(f"Label {label.name} import failed: {import_response.text}")


def _import_project_milestones(
    fg_api: pyforgejo,
    milestones: List[gitlab.v4.objects.ProjectMilestone],
    owner: string,
    repo: string,
):
    """import milestones for a repository"""
    for milestone in milestones:
        if not milestone_exists(fg_api, owner, repo, milestone.title):
            due_date = None
            if milestone.due_date is not None and milestone.due_date != "":
                due_date = dateutil.parser.parse(milestone.due_date).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                )

            import_response: requests.Response = fg_api.post(
                f"/repos/{owner}/{repo}/milestones",
                json={
                    "description": milestone.description,
                    "due_on": due_date,
                    "title": milestone.title,
                },
            )
            if import_response.ok:
                print_info(f"Milestone {milestone.title} imported!")
                existing_milestone = import_response.json()

                if existing_milestone:
                    # update milestone state, this cannot be done in the initial import :(
                    # ? TODO: Forgejo api ignores the closed state...
                    update_response: requests.Response = fg_api.patch(
                        f"/repos/{owner}/{repo}/milestones/{existing_milestone['id']}",
                        json={
                            "description": milestone.description,
                            "due_on": due_date,
                            "title": milestone.title,
                            "state": milestone.state,
                        },
                    )
                    if update_response.ok:
                        print_info(f"Milestone {milestone.title} updated!")
                    else:
                        print_error(
                            f"Milestone {milestone.title} update failed: {update_response.text}"
                        )
            else:
                print_error(
                    f"Milestone {milestone.title} import failed: {import_response.text}"
                )


def _import_project_issues(
    fg_api: pyforgejo,
    issues: List[gitlab.v4.objects.ProjectIssue],
    owner: string,
    repo: string,
):
    # reload all existing milestones and labels, needed for assignment in issues
    existing_milestones = get_milestones(fg_api, owner, repo)
    existing_labels = get_labels(fg_api, owner, repo)

    for issue in issues:
        if not issue_exists(fg_api, owner, repo, issue.title):
            due_date = ""
            if issue.due_date is not None:
                due_date = dateutil.parser.parse(issue.due_date).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                )

            assignee = None
            if issue.assignee is not None:
                assignee = issue.assignee["username"]

            assignees = []
            for tmp_assignee in issue.assignees:
                assignees.append(tmp_assignee["username"])

            milestone = None
            if issue.milestone is not None:
                existing_milestone = next(
                    (
                        item
                        for item in existing_milestones
                        if item["title"] == issue.milestone["title"]
                    ),
                    None,
                )
                if existing_milestone:
                    milestone = existing_milestone["id"]

            labels = []
            for label in issue.labels:
                existing_label = next(
                    (item for item in existing_labels if item["name"] == label), None
                )
                if existing_label:
                    labels.append(existing_label["id"])

            import_response: requests.Response = fg_api.post(
                f"/repos/{owner}/{repo}/issues",
                json={
                    "assignee": assignee,
                    "assignees": assignees,
                    "body": issue.description,
                    "closed": issue.state == "closed",
                    "due_on": due_date,
                    "labels": labels,
                    "milestone": milestone,
                    "title": issue.title,
                },
            )
            if import_response.ok:
                print_info(f"Issue {issue.title} imported!")
            else:
                print_error(
                    f"Issue {issue.title} import failed: {import_response.text}"
                )


def _import_project_repo(fg_api: pyforgejo, project: gitlab.v4.objects.Project):
    if not repo_exists(fg_api, project.namespace["name"], name_clean(project.name)):
        clone_url = project.http_url_to_repo
        if GITLAB_ADMIN_PASS == "" and GITLAB_ADMIN_USER == "":
            clone_url = project.ssh_url_to_repo
        private = project.visibility == "private" or project.visibility == "internal"

        owner = get_user_or_group(project)
        if owner:
            import_response: requests.Response = repo_migrate.sync_detailed(
                body=MigrateRepoOptions(
                    auth_password=GITLAB_ADMIN_PASS,
                    auth_username=GITLAB_ADMIN_USER,
                    clone_addr=clone_url,
                    description=project.description,
                    mirror=False,
                    private=private,
                    repo_name=name_clean(project.name),
                    uid=owner["id"],
                ),
                client=fg_api,
            )
            if import_response.status_code.name == "CREATED":
                print_info(f"Project {name_clean(project.name)} imported!")
            else:
                err_message = json.loads(import_response.content)["message"]
                print_error(
                    f"Project {name_clean(project.name)} "
                    + f"import failed: {err_message}"
                )
        else:
            print_error(
                f"Failed to load project owner for project {name_clean(project.name)}"
            )


def _import_project_repo_collaborators(
    fg_api: pyforgejo,
    collaborators: List[gitlab.v4.objects.ProjectMember],
    project: gitlab.v4.objects.Project,
):
    """import collaborators for a repository"""
    for collaborator in collaborators:
        proj_name = project.namespace["name"]
        clean_proj_name = name_clean(project.name)
        if not collaborator_exists(
            fg_api, proj_name, clean_proj_name, collaborator.username
        ):
            permission = "read"
            if collaborator.access_level == 10:  # guest access
                permission = "read"
            elif collaborator.access_level == 20:  # reporter access
                permission = "read"
            elif collaborator.access_level == 30:  # developer access
                permission = "write"
            elif collaborator.access_level == 40:  # maintainer access
                permission = "admin"
            elif collaborator.access_level == 50:  # owner access (only for groups)
                print_error("Groupmembers are currently not supported!")
                continue  # groups are not supported
            else:
                print_warning(
                    f"Unsupported access level {collaborator.access_level}, "
                    + "setting permissions to 'read'!"
                )

            proj_name = project.namespace["name"]
            clean_proj_name = name_clean(project.name)
            import_response: requests.Response = fg_api.put(
                f"/repos/{proj_name}/{clean_proj_name}/collaborators/{collaborator.username}",
                json={"permission": permission},
            )
            if import_response.ok:
                print_info(f"Collaborator {collaborator.username} imported!")
            else:
                print_error(
                    f"Collaborator {collaborator.username} import failed: {import_response.text}"
                )


def _import_users(
    fg_api: pyforgejo, users: List[gitlab.v4.objects.User], notify: bool = False
):
    """import users and their public keys"""
    if not user_exists(fg_api, "redirect"):
        rnd_str = "".join(random.choices(string.ascii_uppercase + string.digits, k=10))
        tmp_password = f"Tmp1!{rnd_str}"
        # Some gitlab instances do not publish user emails, so we use a dummy email
        body = CreateUserOption(
            email="redirect@noemail-git.local",
            full_name="redirect",
            login_name="redirect",
            password=tmp_password,
            send_notify=False,
            source_id=0,  # local user
            username="redirect",
        )
        import_response: requests.Response = admin_create_user.sync_detailed(
            body=body, client=fg_api
        )
        if import_response.status_code.name == "CREATED":
            print_info(f"User redirect imported, temporary password: {tmp_password}")
        else:
            msg = json.loads(import_response.content)["message"]
            print_error(f"User redirect import failed: {msg}")

    for user in users:
        keys: List[gitlab.v4.objects.UserKey] = user.keys.list(all=True)

        print(f"Importing user {user.username}...")
        print(f"Found {len(keys)} public keys for user {user.username}")

        if not user_exists(fg_api, user.username):
            rnd_str = "".join(
                random.choices(string.ascii_uppercase + string.digits, k=10)
            )
            tmp_password = f"Tmp1!{rnd_str}"
            # Some gitlab instances do not publish user emails, so we use a dummy email
            tmp_email = f"{user.username}@noemail-git.local"
            try:
                tmp_email = user.email
            except AttributeError:
                pass
            body = CreateUserOption(
                email=tmp_email,
                full_name=user.name,
                login_name=user.username,
                password=tmp_password,
                send_notify=notify,
                source_id=0,  # local user
                username=user.username,
            )
            import_response: requests.Response = admin_create_user.sync_detailed(
                body=body, client=fg_api
            )
            if import_response.status_code.name == "CREATED":
                print_info(
                    f"User {user.username} imported, temporary password: {tmp_password}"
                )
            else:
                msg = json.loads(import_response.content)["message"]
                print_error(f"User {user.username} import failed: {msg}")

        # import public keys
        _import_user_keys(fg_api, keys, user)


def _import_user_keys(
    fg_api: pyforgejo,
    keys: List[gitlab.v4.objects.UserKey],
    user: gitlab.v4.objects.User,
):
    """import public keys for a user"""
    for key in keys:
        if not user_key_exists(fg_api, user.username, key.title):
            import_response: requests.Response = admin_create_public_key.sync_detailed(
                username=user.username,
                body=CreateKeyOption(
                    key=key.key,
                    read_only=True,
                    title=key.title,
                ),
                client=fg_api,
            )
            if import_response.status_code.name == "CREATED":
                print_info(f"Public key {key.title} imported!")
            else:
                msg = json.loads(import_response.content)["message"]
                print_error(f"Public key {key.title} import failed: {msg}")


def _import_groups(fg_api: pyforgejo, groups: List[gitlab.v4.objects.Group]):
    """import groups and their members"""
    print(f"Found {len(groups)} gitlab groups")
    print(f"Importing groups... {groups}")
    for group in groups:
        members: List[gitlab.v4.objects.GroupMember] = group.members.list(all=True)

        clean_group_name = name_clean(group.name)
        print(f"Importing group {clean_group_name}...")
        print(f"Found {len(members)} gitlab members for group {name_clean(group.name)}")

        if not organization_exists(fg_api, name_clean(group.name)):
            import_response: requests.Response = org_create.sync_detailed(
                body=CreateOrgOption(
                    description=group.description,
                    full_name=group.full_name,
                    location="",
                    username=name_clean(group.name),
                    website="",
                ),
                client=fg_api,
            )
            if import_response.status_code.name == "CREATED":
                print_info(f"Group {name_clean(group.name)} imported!")
            else:
                msg = json.loads(import_response.content)["message"]
                print_error(f"Group {name_clean(group.name)} import failed: {msg}")
        # import group members
        _import_group_members(fg_api, members, group)


def _import_group_members(
    fg_api: pyforgejo,
    members: List[gitlab.v4.objects.GroupMember],
    group: gitlab.v4.objects.Group,
):
    """import members to a group"""
    # ? TODO: create teams based on gitlab permissions (access_level of group member)
    existing_teams = get_teams(fg_api, name_clean(group.name))
    if existing_teams:
        first_team = existing_teams[0]
        first_team_name = first_team["name"]
        print(
            f"Organization teams fetched, importing users to first team: {first_team_name}"
        )
        for member in members:
            if not member_exists(member.username, first_team["id"]):
                import_response: requests.Response = requests.put(
                    f"{FORGEJO_API_URL}/users/{member.username}",
                    headers={"Authorization": FORGEJO_TOKEN},
                    timeout=10,
                    data={"username": member.username},
                )
                if import_response.ok:
                    print_info(
                        f"Member {member.username} added to group {name_clean(group.name)}!"
                    )
                else:
                    print_error(
                        f"Failed to add member {member.username} to group {name_clean(group.name)}!"
                    )
    else:
        print_error(
            f"Failed to import members to group {name_clean(group.name)}: no teams found!"
        )


#
# Import functions
#


def import_users(gitlab_api: gitlab.Gitlab, fg_api: pyforgejo, notify=False):
    """import all users and groups"""
    # read all users
    users: List[gitlab.v4.objects.User] = gitlab_api.users.list(all=True)

    print(f"Found {len(users)} gitlab users as user {gitlab_api.user.username}")

    # import all non existing users
    _import_users(fg_api, users, notify)


def import_groups(gitlab_api: gitlab.Gitlab, fg_api: pyforgejo):
    """import all users and groups"""
    # read all users
    groups: List[gitlab.v4.objects.Group] = gitlab_api.groups.list(all=True)

    print(f"Found {len(groups)} gitlab groups as user {gitlab_api.user.username}")

    # import all non existing groups
    _import_groups(fg_api, groups)


def import_projects(gitlab_api: gitlab.Gitlab, fg_api: pyforgejo):
    """read all projects and their issues"""
    projects: gitlab.v4.objects.Project = gitlab_api.projects.list(all=True)

    print(f"Found {len(projects)} gitlab projects as user {gitlab_api.user.username}")

    for project in projects:
        collaborators: List[gitlab.v4.objects.ProjectMember] = project.members.list(
            all=True
        )
        # labels: List[gitlab.v4.objects.ProjectLabel] = project.labels.list(all=True)
        # milestones: List[gitlab.v4.objects.ProjectMilestone] = project.milestones.list(
        #     all=True
        # )
        # issues: List[gitlab.v4.objects.ProjectIssue] = project.issues.list(all=True)

        proj_name = project.namespace["name"]
        clean_proj_name = name_clean(project.name)
        print(f"Importing project {clean_proj_name} from owner {proj_name}")
        print(f"Found {len(collaborators)} collaborators for project {clean_proj_name}")
        #print(f"Found {len(labels)} labels for project {clean_proj_name}")
        #print(f"Found {len(milestones)} milestones for project {clean_proj_name}")
        #print(f"Found {len(issues)} issues for project {clean_proj_name}")

        # import project repo
        _import_project_repo(fg_api, project)

        # import collaborators
        # _import_project_repo_collaborators(fg_api, collaborators, project)

        # import labels
        # _import_project_labels(
        #    fg_api, labels, project.namespace["name"], name_clean(project.name)
        # )

        # import milestones
        # _import_project_milestones(
        #    fg_api, milestones, project.namespace["name"], name_clean(project.name)
        # )

        # import issues
        # _import_project_issues(
        #    fg_api, issues, project.namespace["name"], name_clean(project.name)
        # )


#
# Helper functions
#


class Bcolors:
    """Color definitions for console output"""

    HEADER = "\033[95m"
    OKBLUE = "\033[94m"
    OKGREEN = "\033[92m"
    WARNING = "\033[93m"
    FAIL = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"


def color_message(color, message, colorend=Bcolors.ENDC, bold=False):
    """Returns a message in color"""
    if bold:
        return Bcolors.BOLD + color_message(color, message, colorend, False)

    return color + message + colorend


def print_color(color, message, colorend=Bcolors.ENDC, _bold=False):
    """Prints a message in color"""
    print(color_message(color, message, colorend))


def print_info(message):
    """Prints an info message"""
    print_color(Bcolors.OKBLUE, message)


def print_success(message):
    """Prints a success message"""
    print_color(Bcolors.OKGREEN, message)


def print_warning(message):
    """Prints a warning message"""
    print_color(Bcolors.WARNING, message)


def print_error(message):
    """Prints an error message and increments the global error count"""
    global GLOBAL_ERROR_COUNT  # pylint: disable=global-statement
    GLOBAL_ERROR_COUNT += 1
    print_color(Bcolors.FAIL, message)


def name_clean(name):
    """Cleans a name for usage in Forgejo"""
    new_name = name.replace(" ", "_")
    new_name = re.sub(r"[^a-zA-Z0-9_\.-]", "-", new_name)

    if new_name.lower() == "plugins":
        return f"{new_name}-user"

    return new_name


if __name__ == "__main__":
    main()
