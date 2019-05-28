from c7n_mailer.smtp_delivery import SmtpDelivery


class AzureSmtpDelivery(SmtpDelivery):

    def __init__(self, config, session, logger):
        smtp_server = config['smtp_server']
        smtp_port = int(config.get('smtp_port', 25))
        smtp_ssl = bool(config.get('smtp_ssl', True))
        smtp_username = config.get('smtp_username')
        smtp_password = config.get('smtp_password')
        super(AzureSmtpDelivery, self).__init__(smtp_server=smtp_server,
                                                smtp_port=smtp_port,
                                                smtp_ssl=smtp_ssl,
                                                smtp_username=smtp_username,
                                                smtp_password=smtp_password)
