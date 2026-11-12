# A-2 (docs/specs/2026-11-06-a-agent.md): the agent by name, through the mock's DNS on the host's port 5353.
printf 'hello Daphnis\nbye\n' | ./agent -d 10.0.2.2:5353 api.mock 8080
