#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Cron wrapper for python 2.7 and unix. Wrap your cron job to improve monitoring flexibility.

examples:

    superwrap.py -h
    superwrap.py --name foo --cmd='ls -l'

responds to environment variables (these are overridden by command-line params with the same names):

* SUPERWRAP_SMTP_HOST
* SUPERWRAP_MAIL_TO or MAILTO
* SUPERWRAP_MAIL_FROM

also see:

* https://github.com/Doist/cronwrap

"""

import argparse
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import getpass
import os
import smtplib
import socket
import tempfile
import time


# mimic gmail's monospace formatting
HTML_TMPL = """<div style="font-family:monospace; font-size:13px;">%s</div>"""

# message to send on successful completion
STANDARD_MSG_TMPL = """%scommand:

    %s

completed in %.2f seconds
host: %s
user: %s
output written to: %s
stderr written to: %s
"""


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
    def __init__(self, command, args_outfile=None, args_errfile=None):
        outfile = args_outfile if args_outfile else tempfile.mkstemp()[1]
        errfile = args_errfile if args_errfile else tempfile.mkstemp()[1]

        # TODO: this is bash specific - use python subprocess instead
        t_start = time.time()
        self.return_code = os.system("( %s ) > %s 2> %s" % (command, outfile, errfile))
        self.run_time = time.time() - t_start
        self.stdout = open(outfile, "r").read().strip()
        self.stderr = open(errfile, "r").read().strip()

        if not args_outfile:
            os.remove(outfile)
        if not args_errfile:
            os.remove(errfile)


class Mailer:
    """Send a fancy email message, formatted in html to give us a monospace font"""
    def __init__(self, smtp_host, from_addr, to_addrs, subject_prefix, testing_mode):
        self.smtp_args = {}
        if smtp_host:
            self.smtp_args['host'] = smtp_host
        self.from_addr = from_addr
        self.to_addrs = ",".join(to_addrs)
        self.subject_prefix = subject_prefix
        self.testing_mode = True if testing_mode is True else False

    @staticmethod
    def format_message_as_html(message):
        """Take a message and format it in a nice monospace font."""
        html = message.replace(r'  ', ' &nbsp;').replace('\n', '\n<br>').replace('\r', '')
        return HTML_TMPL % html

    def send_email(self, subject, body):
        # see http://docs.python.org/2/library/email-examples.html#id5
        msg = MIMEMultipart('alternative')
        msg['Subject'] = "%s %s" % (self.subject_prefix, subject) if self.subject_prefix else subject
        msg['From'] = self.from_addr
        msg['To'] = self.to_addrs
        msg.attach(MIMEText(body, 'plain'))
        msg.attach(MIMEText(Mailer.format_message_as_html(body), 'html'))  # html content should be last
        if self.testing_mode:
            print msg
        else:
            try:
                s = smtplib.SMTP(**self.smtp_args)
                #s.set_debuglevel(True)
                s.sendmail(self.from_addr, self.to_addrs, msg.as_string())
            finally:
                s.quit()


def _go(args):
    cmd = Command(args.cmd, args.stdout_path, args.stderr_path)

    mailer = Mailer(args.smtp_host, args.mail_from, args.mail_to, args.mail_subject_prefix, args.testing_email_mode)
    hostname = socket.gethostname()
    username = getpass.getuser()
    desc = "%s\n\n" % args.desc if args.desc else ""
    info_msg = STANDARD_MSG_TMPL % (desc, args.cmd, cmd.run_time, hostname, username, args.stdout_path,
                                    args.stderr_path)

    if cmd.return_code != 0 or cmd.stderr:
        # error condition
        subject = "failure: %s" % (args.name)
        body = "%s\n\nstandard error:\n\n%s" % (info_msg, cmd.stderr)
        mailer.send_email(subject, body)
    elif args.email_on_success:
        # success condition, and we want to be notified
        subject = "success: %s" % (args.name)
        body = info_msg
        mailer.send_email(subject, body)


if __name__ == '__main__':
    # command line options
    parser = argparse.ArgumentParser(description='Wrap a cron job to improve monitoring flexibility.')

    # required
    parser.add_argument('-c', '--cmd', required=True, help='The command itself')
    parser.add_argument('-n', '--name', required=True, help='A name, used to identify this cron job. '
                                                            'Choose something unique.')

    # optional
    parser.add_argument('--desc', help='Some text to describe the purpose of the command being run.')
    parser.add_argument('--stdout-path', help='Filename to store standard out (defaults to tmp file)')
    parser.add_argument('--stderr-path', help='Filename to store standard error (defaults to tmp file)')
    parser.add_argument('--mail-to', action='append', help='Send to this address (multiple allowed)')
    parser.add_argument('--mail-from', help='Send from this address')
    parser.add_argument('--mail-subject-prefix', required=False,
                        help='Add a string to the beginning of the subject line')
    parser.add_argument('--smtp-host', help='SMTP host (e.g., mail.foo.com)')
    parser.add_argument('--email-on-success', action='store_true',
                        help='If set, we will send an email on successful completion of CMD.')
    parser.add_argument('--suppress-email-on-stderr', action='store_true',
                        help='If set, we will not email in the presence of output to stderr '
                             '(only on an error return code).')
    parser.add_argument('--testing-email-mode', action='store_true',
                        help='If set, we will just print the email to stdout rather than sending anything.')
    args = parser.parse_args()

    # add environment variable configuration
    if not args.smtp_host:
        args.smtp_host = os.environ.get('SUPERWRAP_SMTP_HOST')
    if not args.mail_to:
        args.mail_to = [os.environ.get('SUPERWRAP_MAIL_TO')]
        if not args.mail_to:
            # check standard crontab env var
            args.mail_to = [os.environ.get('MAILTO')]
    if not args.mail_from:
        args.mail_from = os.environ.get('SUPERWRAP_MAIL_FROM')

    # verify our environment
    if not args.smtp_host:
        raise ValueError("Requires --smtp-host or environment variable SUPERWRAP_SMTP_HOST")

    if not args.mail_to:
        raise ValueError("Requires --mail-to or environment variable SUPERWRAP_MAIL_TO")

    if not args.mail_from:
        raise ValueError("Requires --mail-from or environment variable SUPERWRAP_MAIL_FROM")

    _go(args)
