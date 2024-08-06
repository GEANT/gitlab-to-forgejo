# Gitlab to Forgejo migration script

## --== WIP ==--

**While the script seems to work it has not been tested extensively**

This script uses the Gitlab and Forgejo API's to migrate all data from
Gitlab to Forgejo.

This script support migrating the following data:

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
python3 -m venv migration-env
source migration-env/bin/activate
python3 -m pip install -r requirements.txt
```

Then start the migration script `python3 migrate.py`

### ini file

You need to create a configuration file called `.migrate.ini` and store it in the same directory of the script.  
:bulb: `.migrate.ini` has been added to `.gitignore`.

```ini
[migrate]
gitlab_url = https://gitlab.example.com
gitlab_token = <your-gitlab-token>
gitlab_admin_user = gitlab-user
gitlab_admin_pass = <your-gitlab-password>
forgejo_url = https://forgejo.example.com
forgejo_token = <your-forgejo-token>
```

### Credits and fork information

This is a fork of [gitlab_to_gitea](https://git.autonomic.zone/kawaiipunk/gitlab-to-gitea.git), with less features (this script does not import issues, milestones and labels)
