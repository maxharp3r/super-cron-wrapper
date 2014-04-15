#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Cron wrapper for python 2.7 and unix. Wrap your cron job to improve monitoring flexibility.

examples:

    ./superwrap.py --name foo --mail-to to@nowhere.com --mail-from from@nowhere.com --email-on-success --include-stdout-in-email --testing-email-mode --cmd="ls -l"
    ./superwrap.py --name foo --mail-to to@nowhere.com --mail-from from@nowhere.com --email-on-success --include-stdout-in-email --testing-email-mode --cmd="ls -l asdf"

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

SUBJECT_LINE_TMPL = "%(result)s: %(username)s@%(hostname)s %(name)s"

STANDARD_MSG_TMPL = """%(desc)scommand:

    %(cmd)s

completed in: %(run_time).2f seconds
return code: %(return_code)s
host: %(hostname)s
user: %(username)s
output written to: %(outfile)s (%(outfile_size)d bytes)
stderr written to: %(errfile)s (%(errfile_size)d bytes)
"""

STDOUT_MSG_TMPL = """
standard out:

%s
"""

ERROR_MSG_TMPL = """
standard error:

%s
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


def _truncate(str, maxlen=10000):
    """truncate a string to at most maxlen bytes"""
    return str \
        if len(str) <= maxlen \
        else str[:maxlen] + "...\n(truncated, showing %d of %d characters)" % (maxlen, len(str))


def _go(args):
    """Run the command, send an email if warranted."""
    cmd = Command(args.cmd, args.stdout_path, args.stderr_path)
    succeeded = False \
        if (cmd.return_code != 0 or (not args.ignore_stderr and cmd.stderr)) \
        else True

    if succeeded is True and args.email_on_success is False:
        # success!  we're done
        return

    mailer = Mailer(args.smtp_host, args.mail_from, args.mail_to, args.mail_subject_prefix, args.testing_email_mode)
    cmd_info = {
        "result": "success" if succeeded else "failure",
        "name": args.name,
        "desc": "%s\n\n" % args.desc if args.desc else "",
        "cmd": args.cmd,
        "run_time": cmd.run_time,
        "return_code": cmd.return_code,
        "hostname": socket.gethostname(),
        "username": getpass.getuser(),
        "outfile": args.stdout_path or '/dev/null',
        "outfile_size": len(cmd.stdout),
        "errfile": args.stderr_path or '/dev/null',
        "errfile_size": len(cmd.stderr)
    }
    subject = SUBJECT_LINE_TMPL % cmd_info
    body = STANDARD_MSG_TMPL % cmd_info
    if cmd.stderr:
        body += ERROR_MSG_TMPL % _truncate(cmd.stderr, 100000)
    if args.include_stdout_in_email and cmd.stdout:
        body += STDOUT_MSG_TMPL % _truncate(cmd.stdout)
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

    # optional flags to control behavior
    parser.add_argument('--email-on-success', action='store_true',
                        help='If set, we will send an email on successful completion of CMD.')
    parser.add_argument('--include-stdout-in-email', action='store_true',
                        help='If set, we will include stdout in the email message.')
    parser.add_argument('--ignore-stderr', action='store_true',
                        help='If set, we will only compute success/failur based on the return code of CMD, and will '
                             'ignore output to stderr.')
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
    if not args.smtp_host and not args.testing_email_mode:
        raise ValueError("Requires --smtp-host or environment variable SUPERWRAP_SMTP_HOST")

    if not args.mail_to:
        raise ValueError("Requires --mail-to or environment variable SUPERWRAP_MAIL_TO")

    if not args.mail_from:
        raise ValueError("Requires --mail-from or environment variable SUPERWRAP_MAIL_FROM")

    _go(args)
