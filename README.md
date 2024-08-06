# Gitlab to Forgejo migration script

## --== WIP ==--

This script uses the Gitlab and Forgejo API's to migrate all data from
Gitlab to Forgejo.

This script support migrating the following data:

* Repositories & Wiki (fork status is lost)
* Users (no profile pictures)
* Groups
* Public SSH keys

Tested with Gitlab Version 17.2.1 and Forgejo Version 8.0.0

## Usage

Change items in the config section of the script.

Install all dependencies via `python -m pip install -r requirements.txt` and
use python3 to execute the script.

### How to use with venv

To keep your local system clean, it might be helpful to store all Python dependencies in one folder.
Python provides a virtual environment package which can be used to accomplish this task.

```bash
python3 -m venv migration-env
source migration-env/bin/activate
python3 -m pip install -r requirements.txt
```

Then start the migration script `python3 migrate.py`

### Credits and fork information

this is a fork of [gitlab_to_gitea](https://git.autonomic.zone/kawaiipunk/gitlab-to-gitea.git), with less features (this script does not import issues, milestones and labes)
