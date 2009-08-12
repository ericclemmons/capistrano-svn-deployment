#!/usr/bin/python
import sys, os, re, subprocess, time, shutil, logging, smtplib
from optparse import OptionParser
from email.mime.text import MIMEText

class Deployment:
    
    def __init__(self):
        usage = "usage: %prog [options] app"
        
        parser = OptionParser(usage=usage)
        parser.add_option("-v", "--verbose", action="store_true",  dest="verbose",
                                             help="Enable logging")
        parser.add_option("-q", "--quiet",   action="store_false", dest="verbose",
                                             help="Disable logging")
        parser.add_option("-f", "--force",   action="store_true",  dest="force",
                                             help="Force conditional steps, such as tagging")
        parser.add_option("-t", "--tests",   action="store_true",  dest="tests",
                                             help="Deploy tests only")
        parser.add_option('-s', "--stage",   action="store_const", dest="env", const="stage",
                                             help="Deployments go to staging tier")
        parser.add_option("-r", "--rollback",action="store_true",  dest="rollback",
                                             help="Rollback to the previous release")
        
        (options, args) = parser.parse_args()
        
        self.options = options
        
        if len(args) != 1:
            parser.error("No application or website passed")
        
        self.app = args[0]
    
    def cleanup(self):
        logging.info("Cleaning up old releases...")
        self.run_script("cleanup")
        logging.info("  Done.")
    
    def create_script(self, repository, servers):
        logging.info("    Creating custom deploy.rb...")
        
        script = """
            set :application, "%s"
            set :repository,  "%s"
            
            set :deploy_to, "/usr/local/apache/data/apps/#{application}"
            set :deploy_via, :export
            
            role :web, %s, :primary => true
            
            set :user, "devel"
            set :use_sudo, false
            
            deploy.task :finalize_update do
                # nothing
            end
            
            deploy.task :restart do
                # nothing
            end
        """ % (self.app, repository, servers)
        
        script_path = "%s/config/deploy.rb" % self.get_tmp_folder()
        
        logging.info("      Writing new deployment script to %s" % script_path)
        f = open("%s" % script_path, 'w')
        f.write(script)
    
    def deploy(self, tier):
        if self.options.rollback:
            self.rollback()
        
        logging.info("Beginning %s deployment for %s" % (tier, self.app))
        
        if tier == "production":
            self.deploy_tag()
        else:
            self.deploy_tests()
        
        logging.info("Finished %s deployment for %s." % (tier, self.app))
    
    def deploy_tag(self):
        self.tag()
        self.init_capistrano()
        
        repository = "%s/tags/%s" % (self.get_repository(), self.get_revision("trunk"))
        self.create_script(repository, self.get_servers())
        
        logging.info("Deploying to %s (%s)" % (self.get_env(), self.get_servers()))
        
        self.init_servers()
        self.cleanup()
        self.update()
    
    def deploy_tests(self):
        if self.get_env() != "stage":
            self.set_env("tests")
        
        tests = self.get_tests()
        
        total = len(tests)
        
        if total > 0:
            servers = self.servers[self.get_env()]
            
            if (total > len(servers)):
                logging.error("There are more tests than there are servers! (%s > %s)" % (tests, servers))
                pass
            
            tiers = self.split_list(servers, total)
            
            for i, test in enumerate(tests):
                tier = tiers[i]
                logging.info("  Deploying test \"%s\" (%s/%s) to testing-tier #%s (%s)"
                             % (test, i+1, total, i+1, ", ".join(tier)))
                
                repository = "%s/tests/%s" % (self.get_repository(), test)
                self.create_script(repository, self.get_servers(tier))
                self.update()
                
                logging.info("  Finished deploying test: %s" % test)
                
                # self.notify("Test Deployment <php@whitefence.com>",
                #                             self.mail_to,
                #                             '[%s] Test "%s" (%s of %s) has been deployed' % (self.app, test, i+1, total),
                #                             "Contact php@whitefence.com if you have any questions.")
                
        else:
            logging.info("No tests to deploy.")
    
    def get_app_url(self, repository, app):
        return "%s/%s" % (repository, app)
    
    def get_env(self):
        return self.options.env if self.options.env else "production"
    
    def get_folder(self, file = __file__):
        return os.path.abspath(os.path.dirname(file))
    
    def get_log_filename(self, path = "/"):
        return "%s/%s.r%s" % (self.get_log_folder(), self.app, self.get_revision(path))
    
    def get_log_folder(self):
        # Adjust log path
        log_folder = "%s/deployment" % self.log_folder
        
        # Create log folder
        if not os.path.isdir(log_folder):
            os.makedirs(log_folder)
        
        return log_folder
    
    def get_repository(self):
        for repository in self.repositories:
            url = self.get_app_url(repository, self.app)
            result = self.run("svn list %s" % url)
            
            if result["status"] == 0:
                return url
        
        logging.critical('App "%s" was not found in any of the repositories: %s' % (self.app, self.repositories))
    
    def get_revision(self, path = "/"):
        # svn info on app's root increments with tags.  Check according to path.
        script = "svn info %s/%s" % (self.get_repository(), path)
        result = self.run(script)
        
        logging.debug(script)
        logging.debug(result)
        
        expression = re.compile(r"^Last Changed Rev: (\d+)$", re.M)
        m = re.search(expression, result["output"])
        
        revision = m.group(1)
        logging.info('Latest revision of %s (at "%s") is %s.' % (self.app, path, revision))
        
        return int(revision)
    
    def get_servers(self, servers=None):
        # Turn ["a", "b"] into the string: "a", "b"
        if servers == None:
            servers = self.servers[self.get_env()]
        
        return '"%s"' % '", "'.join(servers)
    
    def get_tags(self):
        result = self.run("svn list %s/tags" % self.get_repository())
        
        expression = re.compile(r"^([\w\.-]+)\/$", re.M)
        tags = re.findall(expression, result["output"])
        
        tags = map(int, tags)
        
        tags.sort()
        
        return tags
    
    
    def get_tests(self):
        result = self.run("svn list %s/tests" % self.get_repository())
        
        tests = []
        
        for line in result['output'].split("\n"):
            m = re.search("^([\w-]+)\/$", line)
            if m:
                tests.append(m.group(1))
        return tests
    
    def get_tmp_folder(self):
        return "%s/deployment/%s" % (self.tmp_folder, self.app)
    
    def init_capistrano(self):
        tmp = self.get_tmp_folder()
        logging.info("Preparing folder for Capistrano: %s" % tmp)
        
        # Remove existing folder
        if os.path.isdir(tmp):
            logging.info("  Folder exists!  Removing...")
            shutil.rmtree(tmp)
        
        # Create new folder
        logging.info("  Creating %s" % tmp)
        os.makedirs(tmp)
        
        # Create config file for Capistrano
        logging.info("  Creating Capistrano config directory at %s/config" % tmp)
        os.makedirs("%s/config" % tmp)
        
        # Initialize Capistrano
        logging.info("  Initializing Capistrano in %s" % tmp)
        self.run_script("init")
        logging.info("    Done.")
    
    def init_servers(self):
        logging.info("Intializing remote folders on %s..." % self.get_servers())
        self.run_script("setup")
        logging.info("  Done.")
    
    def notify_prod(self):
        tags = self.get_tags()
        latest = tags.pop()
        previous = tags.pop()
        
        path = "%s/tags" % self.get_repository()
        paths = "%s/%s %s/%s" % (path, previous, path, latest)
        
        comments_file   =   "%s.comments"% self.get_log_filename("trunk")
        summary_file    =   "%s.summary" % self.get_log_filename("trunk")
        diff_file       =   "%s.diff"    % self.get_log_filename("trunk")
        
        logging.info("Saving comments of release to %s" % comments_file)
        self.run("svn log -r%s:%s %s/trunk > %s" % (previous, latest, self.get_repository(), comments_file))
        
        logging.info("Saving summary of release to %s" % summary_file)
        self.run("svn diff --summarize %s > %s" % (paths, summary_file))
        
        logging.info("Saving diff of release to %s" % diff_file)
        self.run("svn diff %s > %s" % (paths, diff_file))
        
        message = """
"%s" has been updated to r%s from r%s.

==================
Commit Comments
==================
%s


==================
Summary of Changes
==================
%s


==================
Diff
==================
%s
        """ % (self.app, latest, previous, open(comments_file).read(), open(summary_file).read(), open(diff_file).read())
        
        self.notify("Site Deployment <php@whitefence.com>",
                    self.mail_to,
                    "[%s] Revision %s Released" % (self.app, latest),
                    message)
    
    def notify(self, sender, sendee, subject, message):
        logging.info("Notifying %s..." % sendee)
        
        message = MIMEText(message)
        message['Subject']  = subject
        message['From']     = sender
        message['To']       = sendee
        
        s = smtplib.SMTP()
        s.connect()
        s.sendmail(sender, [sendee], message.as_string())
        s.quit()
        
        logging.info("  Done.")
    
    def run(self, command, cwd = None):
        p = subprocess.Popen(command, shell =   True,
                                      cwd   =   cwd,
                                      stdout=   subprocess.PIPE,
                                      stderr=   subprocess.PIPE)
        
        p.wait()
        
        output = p.stdout.readlines() # if p.returncode == 0 else p.stderr.readlines()
        
        return { "status": p.returncode,
                 "output": "\n".join(output) }
    
    def rollback(self):
        logging.info("Rolling back to previous release...")
        self.run_script("rollback")
        logging.info("  Done.")
        exit()
    
    def run_script(self, action):
        script = "./capistrano.sh %s %s" % (action, self.get_tmp_folder())
        result = self.run(script, self.get_folder())
        
        if result["status"] !=0:
            logging.critical(result["output"])
        
        logging.debug("Results from %s\n%s" % (script, result['output']))
        
        return result
    
    def set_env(self, env):
        self.options.env = env
    
    def split_list(self, alist, wanted_parts=1):
        length = len(alist)
        return [ alist[i*length // wanted_parts: (i+1)*length // wanted_parts] 
                 for i in range(wanted_parts) ]
    
    def start(self):
        if self.options.tests:
            self.deploy("tests")
        else:
            self.deploy("production")
            self.deploy("tests")
    
    def tag(self):
        revision = self.get_revision("trunk")
        tags = self.get_tags()
        
        trunk_path = '%s/trunk/' % self.get_repository()
        tag_path = '%s/tags/%s' % (self.get_repository(), revision)
        
        # Don't retag a release if nothing's changed, unless the previous tag
        # fubar'd something, in which case remove the tag & continue
        if tags.count(revision):
            if self.options.force:
                message = "Forcing removal of tag %s for re-deployment." % revision
                logging.info(message)
                commit = 'svn rm %s -m "%s"' % (tag_path, message)
                
                if self.options.verbose != None:
                    logging.info("  Running command: %s" % commit)
                
                self.run(commit)
            else:
                logging.info("This revision has already been tagged.")
                return
        
        message = "Tagging trunk at revision %s..." % revision 
        logging.info(message)
        commit = 'svn cp %s %s -m "%s"' % (trunk_path, tag_path, message)
        
        if self.options.verbose != None:
            logging.info("  Running command: %s" % commit)
        
        self.run(commit)
        
        self.notify_prod()
        
        logging.info("  Done.")
    
    def update(self):
        logging.info("    Updating remote code & symlinks for %s..." % self.get_servers())
        self.run_script("update")
        logging.info("      Done.")
    

