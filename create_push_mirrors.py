#!/usr/bin/env python3
#
"""
Usage: create_push_mirrors.py [--to-forgejo] [--to-gitlab] [--all] [--create] [--delete]
       create_push_mirrors.py --help

Create from Gitlab to Forgejo and vicecersa.

Options
  -h --help         Show this screen
  -f, --to-forgejo  create mirrors from Gitlab to Forgejo
  -g, --to-gitlab   create mirrors from Forgejo to Gitlab
  --all             create mirrors on both directions
"""
import sys
import configparser
import gitlab
import requests
from docopt import docopt

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
GLOBAL_ERROR_COUNT = 0


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


def color_message(color, message, colorend=Bcolors.ENDC, bold=False) -> str:
    """Returns a message in color"""
    if bold:
        return Bcolors.BOLD + color_message(color, message, colorend, False)

    return color + message + colorend


def print_color(color, message, colorend=Bcolors.ENDC, _bold=False) -> None:
    """Prints a message in color"""
    print(color_message(color, message, colorend))


def print_info(message) -> None:
    """Prints an info message"""
    print_color(Bcolors.OKBLUE, message)


def print_success(message) -> None:
    """Prints a success message"""
    print_color(Bcolors.OKGREEN, message)


def print_warning(message) -> None:
    """Prints a warning message"""
    print_color(Bcolors.WARNING, message)


def print_error(message) -> None:
    """Prints an error message and increments the global error count"""
    global GLOBAL_ERROR_COUNT  # pylint: disable=global-statement
    GLOBAL_ERROR_COUNT += 1
    print_color(Bcolors.FAIL, message)


def delete_to_forgejo(gitlab_projects: list) -> None:
    """Delete push mirrors from Gitlab to Forgejo"""
    print_info("Deleting push mirrors from Gitlab")
    for project in gitlab_projects:
        print(f"Project: {project.name_with_namespace}")
        proj_path = project.name_with_namespace
        if project.remote_mirrors.list():
            print_info(f"Push mirrors found on Gitlab for {proj_path}")
            for mirror in project.remote_mirrors.list():
                try:
                    project.remote_mirrors.delete(mirror.id)
                except Exception as err:  # pylint: disable=broad-except
                    print_error(
                        f"Error deleting push mirror on Gitlab for {proj_path}: {err}"
                    )
                else:
                    print_info(f"Push mirrors deleted on Gitlab for {proj_path}")


def delete_to_gitlab(gitlab_projects: list) -> None:
    """Delete push mirrors from Forgejo to Gitlab"""
    print_info("Deleting push mirrors from Forgejo")
    session = requests.Session()
    session.auth = (FORGEJO_USER, FORGEJO_PASSWORD)
    for project in gitlab_projects:
        print(f"Project: {project.name_with_namespace}")
        proj_path = project.name_with_namespace
        forgejo_mirror_url = f"{FORGEJO_API_URL}/repos/puppet/{proj_path}/push_mirrors"
        mirrors = session.get(forgejo_mirror_url).json()
        for mirror in mirrors:
            try:
                project.remote_mirrors.delete(f"{forgejo_mirror_url}/{mirror['remote_name']}")
            except Exception as err:  # pylint: disable=broad-except
                print_error(f"Error deleting push mirror on Forgejo for {proj_path}: {err}")
            else:
                print_info(f"Push mirror deleted on Forgejo for {proj_path}")


def to_forgejo(gitlab_projects: list) -> None:
    """Create push mirrors from Gitlab to Forgejo"""
    print_info("Mirroring repositories from Gitlab to Forgejo")
    for project in gitlab_projects:
        print(f"Project: {project.name_with_namespace}")
        proj_path = project.path_with_namespace
        proj_url = f"{FORGEJO_PREFIX_URL}/{proj_path}.git"
        try:
            project.remote_mirrors.create({"url": proj_url, "enabled": True})
        except Exception as err:  # pylint: disable=broad-except
            print_error(f"Error setting push mirror on Gitlab for {proj_path}: {err}")
        else:
            print_info(f"Push mirror created on Gitlab for {proj_path}")


def to_gitlab(gitlab_projects: list) -> None:
    """Create push mirrors from Forgejo to Gitlab"""
    print_info("Mirroring repositories from Forgejo to Gitlab")

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
        response: requests.Response = session.post(url, json=post_data, rimeout=10)
        if response.ok:
            print_info(f"Error setting push mirror on Forgejo for {proj_path}")
        else:
            print_error(f"Push mirror created on Gitlab for {proj_path}")


if __name__ == "__main__":
    _args = docopt(__doc__)
    args = {k.replace("--", ""): v for k, v in _args.items()}

    gl = gitlab.Gitlab(GITLAB_URL, private_token=GITLAB_TOKEN)
    gl.auth()
    print_info(f"Connected to Gitlab, version: {gl.version()[0]}")
    all_projects = gl.projects.list(all=True)
    print_info(f"Found {len(all_projects)} projects")

    if args["create"] and args["delete"]:
        print_error("You can't create and delete mirrors at the same time")
        sys.exit()

    if args["create"]:
        print_info("Creating mirrors")
        if args["to-forgejo"] or args["all"]:
            to_forgejo(all_projects)

        if args["to-gitlab"] or args["all"]:
            to_gitlab(all_projects)

    if args["delete"]:
        print_info("Deleting mirrors")
        if args["to-forgejo"] or args["all"]:
            delete_to_forgejo(all_projects)

        if args["to-gitlab"] or args["all"]:
            delete_to_gitlab(all_projects)

    print()
    if GLOBAL_ERROR_COUNT == 0:
        print_success("Migration finished with no errors!")
    else:
        print_error(f"Migration finished with {GLOBAL_ERROR_COUNT} errors!")
