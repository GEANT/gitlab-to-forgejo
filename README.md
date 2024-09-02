# Gitlab to Forgejo migration script

## --== WIP ==--

**the scripts are currently undergoing testing**

This script uses the Gitlab API and a combination of Forgejo API and python `requests` to migrate all data from Gitlab to Forgejo.

This script supports migration of the following data:

* Repositories & Wiki (fork status is lost)
* Users (no profile pictures)
* Groups
* Public SSH keys

Tested with Gitlab Version 17.2.1 and Forgejo Version 8.0.0

## Usage

### How to use with venv

To keep your local system clean, it is preferrable to use a virtual environment.
You can follow these steps:

```bash
python3 -m venv migration
source migration/bin/activate
python3 -m pip install -r requirements.txt
```

Then acticate your venv and call the scripts using `--help`:

* `./migrate.py --help`
* `./create_push_mirrors.py --help`

### ini file

You need to create a configuration file called `.migrate.ini` and store it in the same directory of the script.  
:bulb: `.migrate.ini` has been added to `.gitignore`.

```ini
[migrate]
gitlab_url = https://gitlab.example.com
gitlab_token = <your-gitlab-token>
gitlab_admin_user = <gitlab-admin-user>
gitlab_admin_pass = <your-gitlab-password>
forgejo_url = https://forgejo.example.com
forgejo_token = <your-forgejo-token>
forgejo_admin_user = <forgejo-admin-user>
forgejo_admin_pass = <your-forgejo-password>
```

### Credits and fork information

This is a fork of [gitlab_to_gitea](https://git.autonomic.zone/kawaiipunk/gitlab-to-gitea.git), with less features (this script does not import issues, milestones and labels)
