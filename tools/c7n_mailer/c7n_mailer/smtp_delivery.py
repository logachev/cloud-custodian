import smtplib


class SmtpDelivery(object):

    def __init__(self, smtp_server, smtp_port, smtp_ssl, smtp_username, smtp_password):
        smtp_connection = smtplib.SMTP(smtp_server, smtp_port)
        if smtp_ssl:
            smtp_connection.starttls()
            smtp_connection.ehlo()

        if smtp_username or smtp_password:
            smtp_connection.login(smtp_username, smtp_password)

        self._smtp_connection = smtp_connection

    def __del__(self):
        self._smtp_connection.quit()

    def send_message(self, message, to_addrs):
        self._smtp_connection.sendmail(message['From'], to_addrs, message.as_string())
