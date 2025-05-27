## (STATIC) PLAIN Credentials

Server side: `plain-users.json`
```json
{
"kraft": "kraft-secret",
"kafka": "kafka-secret",
"sr": "sr-secret"
}
```

Client side: `plain.txt`
```conf
username=kraft
password=kraft-secret
```


kubectl create secret generic kraft-plain-server --from-file=plain-users.json=plain-users.json
kubectl create secret generic kraft-plain-client --from-file=plain.txt=plain.txt

or both in one:
kubectl create secret generic kraft-creds --from-file=plain-users.json=plain-users.json --from-file=plain.txt=plain.txt

kind: Kafka
spec:
  listeners:
    external:
      authentication:
        type: plain                 --- [1]
        jaasConfig:                 --- [2]
          secretRef: kraft-creds
