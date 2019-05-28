from c7n_mailer.smtp_delivery import SmtpDelivery
from c7n_mailer.utils import kms_decrypt


class AwsSmtpDelivery(SmtpDelivery):

    def __init__(self, config, session, logger):
        smtp_server = config.get['smtp_server']
        smtp_port = int(config.get('smtp_port', 25))
        smtp_ssl = bool(config.get('smtp_ssl', True))
        smtp_username = config.get('smtp_username')
        smtp_password = kms_decrypt(config, logger, session, 'smtp_password')
        super(AwsSmtpDelivery).__init__(smtp_server=smtp_server,
                                        smtp_port=smtp_port,
                                        smtp_ssl=smtp_ssl,
                                        smtp_username=smtp_username,
                                        smtp_password=smtp_password)
