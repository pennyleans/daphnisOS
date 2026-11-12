# A-4 (docs/specs/2026-11-06-a-agent.md): the A-2 session over TLS 1.2, the mock's certificate for api.mock.
printf 'hello Daphnis\nbye\n' | ./agent -d 10.0.2.2:5353 -t api.mock 8443
