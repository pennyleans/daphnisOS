# 07 Networking

Daphnis supports IPv4 over Ethernet with ARP, ICMP echo, UDP, and TCP. The
network stack supports DHCP and has drivers for virtio-net and some Intel
Ethernet controllers. The desktop starts even when it cannot reach a network.

The release image includes `fetch` for HTTP and HTTPS. Network access requires
the Net grant. The command below requests Net access and fetches a file from a
local server.

## Try it in QEMU

Start the `desknet` development image and its mock bridge.

```sh
FAKE=1 tools/run-desk-agent.sh
```

With an HTTP server serving `hello.txt` on the host at port 8000, run this in
the guest terminal.

```sh
grant net fetch http://10.0.2.2:8000/hello.txt
```

With QEMU user networking, `10.0.2.2` addresses the host from the guest.
`check-net.sh` exercises UDP, TCP, and grant enforcement in QEMU.
