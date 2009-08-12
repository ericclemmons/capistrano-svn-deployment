[capistrano]: http://www.capify.org/index.php/Capistrano "Capistrano"
[wf]: http://www.whitefence.com "WhiteFence"
[et]: http://www.electricitytexas.com "ET"

# Sample Capistrano Deployment Script

**For now, this script is based on SVN conventions**

The primary purpose of this script, besides automating deployment is:

*   Automated tagging of releases
*   Deployment of tests to testing servers (for A/B testing)
*   Deployment of latest release to staging environment
*   Notification with commit comments, diffs, etc. for each new release

## Background
I've recently began setting up automated deployment for my various PHP apps to testing, staging
& development servers.  Namely, sites such as [WhiteFence.com][wf], [ElectricityTexas.com][et] and
several other client sites.

I'm moving all of my projects to *Git*, so this script will be modified accordingly.

## How it works

There are 3 files involved with deployment:

*   `deploy`
    
    Defines the *repositores*, *servers*, and *notification email*, as well as how logging is handled.
    
*   deployment.py
    
    Class that actually performs the deployment.  This is highly based on convention.
    
*   capistrano.sh
    
    An `expect` script that performed many of the SVN operations.  This is because various SVN commands
    sent false *EOF* signals to Python (most likely because of child processes spawning) and had to be
    caught via `expect`.

- - -    
## How to use it

### Setup SVN Project Structure

Many of the commands from the script are based on folder structure, which should be as follows:
    
    my-project/
        trunk/
        branches/
        tags/
        tests/

### Configure `deployment.py`

    *todo*

### Deploy

#### Typical Deployment

    # deploy my-project

#### Deploy to staging environment

    # deploy --stage my-project

#### Deploy tests to testing tier

    # deploy --tests my-project

#### Deploy tests to staging tier

    # deploy --tests --stage my-project
    
- - -
## What's going on behind the scenes?

### When deploying to production/stage

1.  Script checks latest revision of `my-project`, `trunk`, and latest `tag`.
2.  If the `trunk` has been modified since last `tag`, a new `tag` is made at that revision.
3.  Script decides testing tier based on the presence of `--stage` switch.
4.  Capistrano script is created for deploying the latest `tag` to the proper tier.
5.  Capistrano script is ran:
    1. Remote deployment folder is initialized.
    2. Old releases are cleaned up.
    3. New release is exported to `/releases` & symlinked to `/current` folder on tier.
6.  If there is an error, Capistrano performs a `--rollback`.
7.  Finished.

### When deploying tests...

The process is the same as above, except that:

*   Tests in the `/tests` folder are not tagged, and are simply deployed as-is.
*   Tests are spread across the testing tier.  For example, if there are *2 tests* and *4 servers*,
    `Test A` will be placed on servers 1 & 2, while `Test B` will be placed on servers 3 & 4.