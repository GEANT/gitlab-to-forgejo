# Gitlab to Forgejo migration script

## Preamble

These scripts are inspired by [gitlab-to-gitea script](https://git.autonomic.zone/kawaiipunk/gitlab-to-gitea.git)

I already tried the original script and it did not work with Forgejo, hence the second part of the script needs to be rewritten, and a different library should be used, among one of the followings: [api-client-libraries](https://codeberg.org/forgejo-contrib/delightful-forgejo#api-client-libraries)

## Description of the tool

This script uses the APIs from both systems to migrate all data from Gitlab to Gitea.

This script support migrating the following data:

* Repositories & Wiki (fork status is lost)
* Milestones
* Labels
* Issues (no comments)
* Users (no profile pictures)
* Groups
* Public SSH keys

Tested with Gitlab Version 13.0.6 and Gitea Version 1.11.6.

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
