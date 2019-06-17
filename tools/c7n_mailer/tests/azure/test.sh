#!/bin/bash

set -e
set -x

location=eastus
rg_name=cloud-custodian-test-mailer$RANDOM
storage_name=custodianstorage$RANDOM
queue_name=mailer-queue

username=${SENDGRID_USERNAME}
password=${SENDGRID_PASSWORD}
smtp_server=smtp.sendgrid.net

function cleanup {
    set +e
    rm -f mailer.yaml
    rm -f notify_policy.yaml
    rf -rf azure-notify
    echo "Removing resource group"
    az group delete -n ${rg_name} -y -o None
}
trap cleanup EXIT

az login --service-principal --username ${AZURE_CLIENT_ID} --password ${AZURE_CLIENT_SECRET} --tenant ${AZURE_TENANT_ID} -o None
az account set -s ${AZURE_SUBSCRIPTION_ID} -o None

az group create -n ${rg_name} -l ${location} -o none
storage_id=$(az storage account create -g ${rg_name} -l ${location} -n ${storage_name} --query id -o tsv)
az storage queue create -n ${queue_name} --account-name ${storage_name} -o none
az role assignment create --role "Storage Queue Data Contributor" --assignee ${AZURE_CLIENT_ID} --scope ${storage_id} -o None

# Render custodian configuration
eval "echo \"$(cat templates/mailer.yaml)\"" > mailer.yaml
eval "echo \"$(cat templates/notify_policy.yaml)\"" > notify_policy.yaml


# Run custodian
custodian run -s=. notify_policy.yaml
c7n-mailer -c mailer.yaml --update-lambda

result=1
max_attempts=60
for i in $(seq 1 ${max_attempts})
do
    sleep 30s
    echo "Query sendgrid..."
    r=$(curl -X "GET" "https://api.sendgrid.com/api/bounces.get.json?api_user=${username}&api_key=${password}&date=1")

    requests=$(echo ${r} | grep -c 'Access denied')
    echo "Number of requests from sendgrid: $requests"

    if [[ ${requests} -eq 1 ]]; then
        result=0
        break
    fi
done

echo "Exit status:${result}"
exit ${result}
