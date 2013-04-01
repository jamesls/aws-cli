  $ export AWS_DEFAULT_REGION=us-west-2
  $ aws ec2 describe-instances | jq '.Reservations[0].Instances[0].Hypervisor'
  "xen"
