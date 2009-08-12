#!/usr/bin/expect -f

set cmd [lrange $argv 0 0]
set wcPath [lrange $argv 1 1]

cd $wcPath

switch -- $::cmd "init" {
        spawn capify $wcPath
    } "setup" {
        spawn cap deploy:setup
    } "cleanup" {
        spawn cap deploy:cleanup
    } "update" {
        spawn cap deploy:update
    } "rollback" {
        spawn cap deploy:rollback:code
    } default {
        print "Supplied command ($cmd) not supported."
        exit 1
    }

while {true} {
    expect {
        "Password" {
            puts "\nPlease copy your SSH public key to the proper hosts first."
            exit 1
        }
        eof {
            exit
        }
    }
}