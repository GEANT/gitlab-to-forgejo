#!/usr/bin/env python3
#
# pylint: disable=line-too-long
"""
Usage: create_push_mirrors.py [--to-forgejo] [--to-gitlab] [--all] [--limit LIMIT] (--create | --delete)
       create_push_mirrors.py --help

Create from Gitlab to Forgejo and vicecersa.

Options
  -h, --help     Show this screen
  --to-forgejo   create mirrors from Gitlab to Forgejo
  --to-gitlab    create mirrors from Forgejo to Gitlab
  --all          create mirrors on both directions
  --limit LIMIT  for testing you can limit the number of projects to migrate [default: 100000]
  --create       create mirrors
  --delete       delete mirrors
"""
# pylint: enable=line-too-long
import os
import configparser
import gitlab
import requests
from docopt import docopt
from fg_migration import fg_print

#######################
# CONFIG SECTION START
#######################
if not os.path.exists(".migrate.ini"):
    fg_print.error("Please create .migrate.ini as explained in the README!")
    os.sys.exit()

config = configparser.RawConfigParser()
config.read(".migrate.ini")
GITLAB_URL = config.get("migrate", "gitlab_url")
GITLAB_TOKEN = config.get("migrate", "gitlab_token")
GITLAB_ADMIN_USER = config.get("migrate", "gitlab_admin_user")
GITLAB_ADMIN_PASS = config.get("migrate", "gitlab_admin_pass")
FORGEJO_URL = config.get("migrate", "forgejo_url")
FORGEJO_API_URL = f"{FORGEJO_URL}/api/v1"
FORGEJO_HOST = FORGEJO_URL.split("/")[-1]
FORGEJO_USER = config.get("migrate", "forgejo_admin_user")
FORGEJO_PASSWORD = config.get("migrate", "forgejo_admin_pass")
FORGEJO_TOKEN = config.get("migrate", "forgejo_token")
FORGEJO_PREFIX_URL = f"https://{FORGEJO_USER}:{FORGEJO_PASSWORD}@{FORGEJO_HOST}"
#######################
# CONFIG SECTION END
#######################


def delete_to_forgejo(gitlab_projects: list) -> None:
    """Delete push mirrors from Gitlab to Forgejo"""
    fg_print.info("\nDeleting push mirrors from Gitlab")
    for project in gitlab_projects:
        print(f"Project: {project.name_with_namespace}")
        proj_path = project.path_with_namespace
        if project.remote_mirrors.list():
            # fg_print.info(f"Push mirrors found on Gitlab for {proj_path}")
            for mirror in project.remote_mirrors.list():
                try:
                    project.remote_mirrors.delete(mirror.id)
                except Exception as err:  # pylint: disable=broad-except
                    fg_print.error(
                        f"Error deleting push mirror on Gitlab for {proj_path}: {err}"
                    )
                else:
                    fg_print.info(f"Push mirrors deleted on Gitlab for {proj_path}")


def delete_to_gitlab(gitlab_projects: list) -> None:
    """Delete push mirrors from Forgejo to Gitlab"""
    fg_print.info("\nDeleting push mirrors from Forgejo")
    session = requests.Session()
    session.auth = (FORGEJO_USER, FORGEJO_PASSWORD)
    for project in gitlab_projects:
        print(f"Project: {project.name_with_namespace}")
        proj_path = project.path_with_namespace
        forgejo_mirror_url = f"{FORGEJO_API_URL}/repos/{proj_path}/push_mirrors"
        mirrors = session.get(forgejo_mirror_url).json()
        for mirror in mirrors:
            mirror_name = mirror["remote_name"]
            # fg_print.info(f"Push mirrors {mirror_name} found on Gitlab for {proj_path}")
            url = f"{forgejo_mirror_url}/{mirror_name}"
            response: requests.Response = session.delete(url, timeout=10)
            if response.ok:
                fg_print.info(
                    f"Push mirror {mirror_name} deleted on Forgejo for {proj_path}"
                )
            else:
                fg_print.error(
                    f"Error deleting push mirror {mirror_name} on Forgejo for {proj_path}"
                )


def to_forgejo(gitlab_projects: list) -> None:
    """Create push mirrors from Gitlab to Forgejo"""
    fg_print.info("\nMirroring repositories from Gitlab to Forgejo")
    for project in gitlab_projects:
        print(f"Project: {project.name_with_namespace}")
        proj_path = project.path_with_namespace
        proj_url = f"{FORGEJO_PREFIX_URL}/{proj_path}.git"
        try:
            project.remote_mirrors.create({"url": proj_url, "enabled": True})
        except Exception as err:  # pylint: disable=broad-except
            fg_print.error(
                f"Error setting push mirror on Gitlab for {proj_path}: {err}"
            )
        else:
            fg_print.info(f"Push mirror created on Gitlab for {proj_path}")


def to_gitlab(gitlab_projects: list) -> None:
    """Create push mirrors from Forgejo to Gitlab"""
    fg_print.info("\nMirroring repositories from Forgejo to Gitlab")

    session = requests.Session()
    session.auth = (FORGEJO_USER, FORGEJO_PASSWORD)
    # session.headers.update({"Authorization": FORGEJO_TOKEN})

    for project in gitlab_projects:
        proj_path = project.path_with_namespace
        url = f"{FORGEJO_API_URL}/repos/{proj_path}/push_mirrors"
        post_data = {
            "interval": "8h0m0s",
            "remote_address": f"{GITLAB_URL}/{proj_path}",
            "remote_password": GITLAB_ADMIN_PASS,
            "remote_username": GITLAB_ADMIN_USER,
            "sync_on_commit": True,
        }
        response: requests.Response = session.post(url, json=post_data, timeout=10)
        if response.ok:
            fg_print.info(f"Push mirror created on Gitlab for {proj_path}")
        else:
            fg_print.error(f"Error setting push mirror on Forgejo for {proj_path}")


if __name__ == "__main__":
    _args = docopt(__doc__)
    args = {k.replace("--", ""): v for k, v in _args.items()}

    gl = gitlab.Gitlab(GITLAB_URL, private_token=GITLAB_TOKEN)
    gl.auth()
    fg_print.info(f"Connected to Gitlab, version: {gl.version()[0]}")
    limit = args["limit"]

    if args["to-forgejo"] or args["to-gitlab"] or args["all"]:
        if limit != "100000":
            all_projects = gl.projects.list(all=False, per_page=limit, page=1)
        else:
            all_projects = gl.projects.list(all=True)
        fg_print.info(f"Found {len(all_projects)} projects")
    else:
        fg_print.error("Please specify --to-forgejo, --to-gitlab or --all")
        os.sys.exit()

    if args["create"]:
        fg_print.info("Creating mirrors")
        if args["to-forgejo"] or args["all"]:
            to_forgejo(all_projects)

        if args["to-gitlab"] or args["all"]:
            to_gitlab(all_projects)

    if args["delete"]:
        fg_print.info("Deleting mirrors")
        if args["to-forgejo"] or args["all"]:
            delete_to_forgejo(all_projects)

        if args["to-gitlab"] or args["all"]:
            delete_to_gitlab(all_projects)

    ERR_COUNT = fg_print.GLOBAL_ERROR_COUNT
    if ERR_COUNT == 0:
        fg_print.success("\nMigration finished with no errors!")
    else:
        fg_print.error(f"\nMigration finished with {ERR_COUNT} errors!")
