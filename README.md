super-cron-wrapper
==================

Cron wrapper for python 2.7 and unix. Wrap your cron job to improve monitoring flexibility.

examples:

    ./superwrap.py --name foo --mail-to to@nowhere.com --mail-from from@nowhere.com --email-on-success --testing-email-mode --cmd="ls -l"
    ./superwrap.py --name foo --mail-to to@nowhere.com --mail-from from@nowhere.com --email-on-success --testing-email-mode --cmd="ls -l asdf"

responds to environment variables (these are overridden by command-line params with the same names):

* SUPERWRAP_SMTP_HOST
* SUPERWRAP_MAIL_TO or MAILTO
* SUPERWRAP_MAIL_FROM

also see:

* https://github.com/Doist/cronwrap
