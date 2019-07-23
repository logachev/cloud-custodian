import yaml
import argparse


def main():
    parser = argparse.ArgumentParser(description='Deploy c7n-azure into Azure Functions.')
    parser.add_argument('--config', '-c', dest='config',
                        help='Path to c7n-azure-deployer configuration file.')

    parser.add_argument('--auth-file', '-a', dest='authentication_file',
                        help='Path to authentication file to use.')
    args = parser.parse_args()

    config_file = args.config
    auth_file = args.authentication_file

    with open(config_file, 'r') as stream:
        config = yaml.safe_load(stream)

    policies_files = config['policies']

    
    print(policies_files)


if __name__ == '__main__':
    main()
