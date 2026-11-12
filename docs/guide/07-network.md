# 07 Network

The stack is cint inside the kernel (NET-1 A): virtio-net, Ethernet, ARP, IPv4, ICMP echo, UDP and TCP. Every received frame
is journaled, so a run replays from its transcript. No process reaches the network without `grant net`.

## What exists

| piece | state |
| --- | --- |
| device | virtio-net on QEMU's user network; one fixed address, `10.0.2.15/24`; the host is `10.0.2.2` |
| UDP | `socket`, `bind`, `sendto`, `recvfrom`, `getsockname` |
| TCP | 8 connections, client and server (`connect`, `listen`, `accept`); one segment in flight, a 4 KiB receive ring |
| names | a stub resolver in cint (`user/ci/dns.ci`): one A query over UDP; `agent -d` uses it |
| TLS | BearSSL 0.6 inside `agent` only |
| tools | busybox-net `wget` (an address, not a name), `talk`, `agent`; test programs `mudp`, `mtcp` |

Throughput is low: one segment in flight, tens of KB/s. No DHCP, no IPv6, no IP fragments, no TCP window above one
segment.

## Try it

The `desknet` flavor is the first desk with the network:

```
tools/run-desk-agent.sh                  # boots desknet with NET=user; see 09-agent.md
```

In its terminal:

```
./grant net wget http://10.0.2.2:8000/hello.txt      # a server on the host, port 8000
wget http://10.0.2.2:8000/hello.txt                  # without the grant: Permission denied
```

Checked by `check-net.sh` (15 checks: the first frame, 8 UDP datagrams to an echo, a 256 KiB `wget` with its
`md5sum`, a TCP echo server the host connects to, the refusal without the grant) and by `check.sh`, which replays the
committed journal.
