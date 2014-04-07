#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Cron wrapper for python 2.7 and unix. Wrap your cron job to improve monitoring flexibility.

examples:

    superwrap.py -h
    superwrap.py --name foo --cmd='ls -l'

responds to environment variables:

* SMTP_HOST (optional, will default to trying a local smtp server)
* MAILTO (required if `--email` command line option is not set)
* MAILFROM (optional, will override the default email from address)

also see:

* https://github.com/Doist/cronwrap

"""

import argparse
from copy import copy
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import os
import smtplib
import tempfile
import time


# mimic gmail's monospace formatting
HTML_TMPL = """<div style="font-family:monospace; font-size:13px;">%s</div>"""


# adapted from https://github.com/Doist/cronwrap
class Command:
    """Runs a command, only works on Unix.

       Example of usage::

           cmd = Command('ls')
           print cmd.stdout
           print cmd.stderr
           print cmd.return_code
           print cmd.run_time
    """
    def __init__(self, command):
        outfile = tempfile.mktemp()
        errfile = tempfile.mktemp()

        t_start = time.time()
        self.return_code = os.system("( %s ) > %s 2> %s" % (command, outfile, errfile))
        self.run_time = time.time() - t_start
        self.stdout = open(outfile, "r").read().strip()
        self.stderr = open(errfile, "r").read().strip()

        os.remove(outfile)
        os.remove(errfile)


class Mailer:
    """Send a fancy email message, formatted in html to give us monospace"""
    def __init__(self, smtp_host, from_addr, to_addrs):
        self.smtp_args = {}
        if smtp_host:
            self.smtp_args['host'] = smtp_host
        self.from_addr = from_addr
        self.to_addrs = to_addrs

    def format_message_as_html(self, message):
        """Take a message and format it in a nice monospace font."""
        html = message.replace(r'  ', ' &nbsp;').replace('\n', '\n<br>').replace('\r', '')
        return HTML_TMPL % (html)

    def send_email(self, subject, body):
        # see http://docs.python.org/2/library/email-examples.html#id5
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = self.from_addr
        msg['To'] = ",".join(self.to_addrs)
        msg.attach(MIMEText(body, 'plain'))
        msg.attach(MIMEText(self.format_message_as_html(body), 'html'))  # html content should be last
        try:
            s = smtplib.SMTP(**self.smtp_args)
            #s.set_debuglevel(True)
            s.sendmail(self.from_addr, self.to_addrs, msg.as_string())
        finally:
            s.quit()


def go(args):
    print args.cmd
    print args.email
    cmd = Command(args.cmd)
    print cmd.stdout
    print cmd.stderr
    print cmd.return_code
    print cmd.run_time

    mailer = Mailer(args.smtp_host, 'hello <foo@bar.com>', [args.email])

    if cmd.return_code != 0 or cmd.stderr:
        # error condition
        pass
    elif args.email_on_success:
        # success condition, and we want to be notified
        subject = "[cron] %s success" % (args.name)
        body = """command:

    %s

completed in %.2f seconds""" % (args.cmd, cmd.run_time)
        mailer.send_email(subject, body)


if (__name__ == '__main__'):
    # command line options
    parser = argparse.ArgumentParser(description='Wrap a cron job to improve monitoring flexibility.')

    # required
    parser.add_argument('-n', '--name', required=True, help='A name, used to identify this cron job. '
                                                            'Choose something unique.')
    parser.add_argument('-c', '--cmd', required=True, help='The command itself')

    # optional
    parser.add_argument('-e', '--email', required=False, help='Email address')
    parser.add_argument('--email-on-success', action='store_true',
                        help='If set, we will send an email on successful completion of CMD.')
    parser.add_argument('--suppress-email-on-stderr', action='store_true',
                        help='If set, we will not email in the presence of output to stderr (just return code).')
    args = parser.parse_args()

    # add environment variable configuration
    args.smtp_host = os.environ.get('SMTP_HOST')
    if not args.email:
        args.email = os.environ.get('MAILTO')
    args.mailfrom = os.environ.get('MAILFROM')

    # verify our environment
    if not args.smtp_host:
        raise ValueError("Requires environment variable SMTP_HOST.")

    if not args.email:
        raise ValueError("Requires an email address (or environment variable MAILTO).")

    go(args)
