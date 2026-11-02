# Policy source overlap audit

This report compares normalized domain sets across discovered publisher feeds. It is informational only: overlap does not prove common ancestry, and low overlap does not prove independence.

- Feeds fetched: **73**
- Cross-policy conflict domains: **814**

| Policy | Publisher A | Publisher B | A domains | B domains | Shared | Smaller-set overlap | Jaccard |
|---|---|---|---:|---:|---:|---:|---:|
| DIRECT | ACL4SSR/ACL4SSR | Clash-FX/cn-apps-direct-domains | 605 | 120 | 73 | 60.8% | 11.2% |
| DIRECT | ACL4SSR/ACL4SSR | Jovanykoch/rules | 605 | 6771 | 439 | 72.6% | 6.3% |
| DIRECT | ACL4SSR/ACL4SSR | YanbingJiang/Shadowrocket_diy_rules | 605 | 408 | 37 | 9.1% | 3.8% |
| DIRECT | ACL4SSR/ACL4SSR | nthack/Shadowrocket-ADBlock-Rules-Easy | 605 | 325 | 35 | 10.8% | 3.9% |
| DIRECT | ACL4SSR/ACL4SSR | tickmao/Rules | 605 | 195 | 6 | 3.1% | 0.8% |
| DIRECT | ACL4SSR/ACL4SSR | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 605 | 325 | 35 | 10.8% | 3.9% |
| DIRECT | Clash-FX/cn-apps-direct-domains | Jovanykoch/rules | 120 | 6771 | 83 | 69.2% | 1.2% |
| DIRECT | Clash-FX/cn-apps-direct-domains | YanbingJiang/Shadowrocket_diy_rules | 120 | 408 | 13 | 10.8% | 2.5% |
| DIRECT | Clash-FX/cn-apps-direct-domains | nthack/Shadowrocket-ADBlock-Rules-Easy | 120 | 325 | 13 | 10.8% | 3.0% |
| DIRECT | Clash-FX/cn-apps-direct-domains | tickmao/Rules | 120 | 195 | 1 | 0.8% | 0.3% |
| DIRECT | Clash-FX/cn-apps-direct-domains | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 120 | 325 | 13 | 10.8% | 3.0% |
| DIRECT | Jovanykoch/rules | YanbingJiang/Shadowrocket_diy_rules | 6771 | 408 | 50 | 12.3% | 0.7% |
| DIRECT | Jovanykoch/rules | nthack/Shadowrocket-ADBlock-Rules-Easy | 6771 | 325 | 42 | 12.9% | 0.6% |
| DIRECT | Jovanykoch/rules | tickmao/Rules | 6771 | 195 | 16 | 8.2% | 0.2% |
| DIRECT | Jovanykoch/rules | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 6771 | 325 | 42 | 12.9% | 0.6% |
| DIRECT | YanbingJiang/Shadowrocket_diy_rules | nthack/Shadowrocket-ADBlock-Rules-Easy | 408 | 325 | 325 | 100.0% | 79.7% |
| DIRECT | YanbingJiang/Shadowrocket_diy_rules | tickmao/Rules | 408 | 195 | 58 | 29.7% | 10.6% |
| DIRECT | YanbingJiang/Shadowrocket_diy_rules | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 408 | 325 | 325 | 100.0% | 79.7% |
| DIRECT | nthack/Shadowrocket-ADBlock-Rules-Easy | tickmao/Rules | 325 | 195 | 1 | 0.5% | 0.2% |
| DIRECT | nthack/Shadowrocket-ADBlock-Rules-Easy | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 325 | 325 | 325 | 100.0% | 100.0% |
| DIRECT | tickmao/Rules | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 195 | 325 | 1 | 0.5% | 0.2% |
| PROXY | ACL4SSR/ACL4SSR | Johnshall/Shadowrocket-ADBlock-Rules-Forever | 6816 | 30183 | 4621 | 67.8% | 14.3% |
| PROXY | ACL4SSR/ACL4SSR | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | 6816 | 39456 | 5627 | 82.6% | 13.8% |
| PROXY | ACL4SSR/ACL4SSR | YanbingJiang/Shadowrocket_diy_rules | 6816 | 5815 | 5156 | 88.7% | 69.0% |
| PROXY | ACL4SSR/ACL4SSR | gatework/surge-rules | 6816 | 4451 | 3786 | 85.1% | 50.6% |
| PROXY | ACL4SSR/ACL4SSR | nthack/Shadowrocket-ADBlock-Rules-Easy | 6816 | 5575 | 5040 | 90.4% | 68.6% |
| PROXY | ACL4SSR/ACL4SSR | sve1r/Rules-For-Quantumult-X | 6816 | 574 | 371 | 64.6% | 5.3% |
| PROXY | ACL4SSR/ACL4SSR | tickmao/Rules | 6816 | 7367 | 6644 | 97.5% | 88.1% |
| PROXY | ACL4SSR/ACL4SSR | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 6816 | 30166 | 4618 | 67.8% | 14.3% |
| PROXY | ACL4SSR/ACL4SSR | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 6816 | 4425 | 3794 | 85.7% | 50.9% |
| PROXY | Johnshall/Shadowrocket-ADBlock-Rules-Forever | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | 30183 | 39456 | 20988 | 69.5% | 43.1% |
| PROXY | Johnshall/Shadowrocket-ADBlock-Rules-Forever | YanbingJiang/Shadowrocket_diy_rules | 30183 | 5815 | 3739 | 64.3% | 11.6% |
| PROXY | Johnshall/Shadowrocket-ADBlock-Rules-Forever | gatework/surge-rules | 30183 | 4451 | 4419 | 99.3% | 14.6% |
| PROXY | Johnshall/Shadowrocket-ADBlock-Rules-Forever | nthack/Shadowrocket-ADBlock-Rules-Easy | 30183 | 5575 | 3619 | 64.9% | 11.3% |
| PROXY | Johnshall/Shadowrocket-ADBlock-Rules-Forever | sve1r/Rules-For-Quantumult-X | 30183 | 574 | 296 | 51.6% | 1.0% |
| PROXY | Johnshall/Shadowrocket-ADBlock-Rules-Forever | tickmao/Rules | 30183 | 7367 | 4933 | 67.0% | 15.1% |
| PROXY | Johnshall/Shadowrocket-ADBlock-Rules-Forever | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 30183 | 30166 | 30161 | 100.0% | 99.9% |
| PROXY | Johnshall/Shadowrocket-ADBlock-Rules-Forever | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 30183 | 4425 | 4401 | 99.5% | 14.6% |
| PROXY | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | YanbingJiang/Shadowrocket_diy_rules | 39456 | 5815 | 4945 | 85.0% | 12.3% |
| PROXY | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | gatework/surge-rules | 39456 | 4451 | 4117 | 92.5% | 10.3% |
| PROXY | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | nthack/Shadowrocket-ADBlock-Rules-Easy | 39456 | 5575 | 4820 | 86.5% | 12.0% |
| PROXY | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | sve1r/Rules-For-Quantumult-X | 39456 | 574 | 320 | 55.7% | 0.8% |
| PROXY | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | tickmao/Rules | 39456 | 7367 | 5717 | 77.6% | 13.9% |
| PROXY | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 39456 | 30166 | 20967 | 69.5% | 43.1% |
| PROXY | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 39456 | 4425 | 4102 | 92.7% | 10.3% |
| PROXY | YanbingJiang/Shadowrocket_diy_rules | gatework/surge-rules | 5815 | 4451 | 2913 | 65.4% | 39.6% |
| PROXY | YanbingJiang/Shadowrocket_diy_rules | nthack/Shadowrocket-ADBlock-Rules-Easy | 5815 | 5575 | 5575 | 100.0% | 95.9% |
| PROXY | YanbingJiang/Shadowrocket_diy_rules | sve1r/Rules-For-Quantumult-X | 5815 | 574 | 306 | 53.3% | 5.0% |
| PROXY | YanbingJiang/Shadowrocket_diy_rules | tickmao/Rules | 5815 | 7367 | 5055 | 86.9% | 62.2% |
| PROXY | YanbingJiang/Shadowrocket_diy_rules | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 5815 | 30166 | 3739 | 64.3% | 11.6% |
| PROXY | YanbingJiang/Shadowrocket_diy_rules | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 5815 | 4425 | 2945 | 66.6% | 40.4% |
| PROXY | gatework/surge-rules | nthack/Shadowrocket-ADBlock-Rules-Easy | 4451 | 5575 | 2816 | 63.3% | 39.1% |
| PROXY | gatework/surge-rules | sve1r/Rules-For-Quantumult-X | 4451 | 574 | 245 | 42.7% | 5.1% |
| PROXY | gatework/surge-rules | tickmao/Rules | 4451 | 7367 | 4131 | 92.8% | 53.7% |
| PROXY | gatework/surge-rules | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 4451 | 30166 | 4419 | 99.3% | 14.6% |
| PROXY | gatework/surge-rules | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 4451 | 4425 | 4390 | 99.2% | 97.9% |
| PROXY | nthack/Shadowrocket-ADBlock-Rules-Easy | sve1r/Rules-For-Quantumult-X | 5575 | 574 | 286 | 49.8% | 4.9% |
| PROXY | nthack/Shadowrocket-ADBlock-Rules-Easy | tickmao/Rules | 5575 | 7367 | 4938 | 88.6% | 61.7% |
| PROXY | nthack/Shadowrocket-ADBlock-Rules-Easy | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 5575 | 30166 | 3620 | 64.9% | 11.3% |
| PROXY | nthack/Shadowrocket-ADBlock-Rules-Easy | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 5575 | 4425 | 2848 | 64.4% | 39.8% |
| PROXY | sve1r/Rules-For-Quantumult-X | tickmao/Rules | 574 | 7367 | 533 | 92.9% | 7.2% |
| PROXY | sve1r/Rules-For-Quantumult-X | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 574 | 30166 | 293 | 51.0% | 1.0% |
| PROXY | sve1r/Rules-For-Quantumult-X | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 574 | 4425 | 248 | 43.2% | 5.2% |
| PROXY | tickmao/Rules | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 7367 | 30166 | 4927 | 66.9% | 15.1% |
| PROXY | tickmao/Rules | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 7367 | 4425 | 4085 | 92.3% | 53.0% |
| PROXY | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 30166 | 4425 | 4401 | 99.5% | 14.6% |
| REJECT | GoodnessJSON/PiHole-Whitelist | Isaaker/Spotify-AdsList | 270 | 155422 | 90 | 33.3% | 0.1% |
| REJECT | GoodnessJSON/PiHole-Whitelist | Johnshall/Shadowrocket-ADBlock-Rules-Forever | 270 | 52060 | 21 | 7.8% | 0.0% |
| REJECT | GoodnessJSON/PiHole-Whitelist | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | 270 | 45081 | 21 | 7.8% | 0.0% |
| REJECT | GoodnessJSON/PiHole-Whitelist | YanbingJiang/Shadowrocket_diy_rules | 270 | 17028 | 3 | 1.1% | 0.0% |
| REJECT | GoodnessJSON/PiHole-Whitelist | anudeepND/whitelist | 270 | 267 | 267 | 100.0% | 98.9% |
| REJECT | GoodnessJSON/PiHole-Whitelist | badmojr/1Hosts | 270 | 0 | 0 | 0.0% | 0.0% |
| REJECT | GoodnessJSON/PiHole-Whitelist | furkan-bayrak/lg-tv-blocklist | 270 | 115 | 0 | 0.0% | 0.0% |
| REJECT | GoodnessJSON/PiHole-Whitelist | marco-acorte/antispam-it | 270 | 346345 | 0 | 0.0% | 0.0% |
| REJECT | GoodnessJSON/PiHole-Whitelist | nthack/Shadowrocket-ADBlock-Rules-Easy | 270 | 16125 | 3 | 1.1% | 0.0% |
| REJECT | GoodnessJSON/PiHole-Whitelist | phishdestroy/destroylist | 270 | 234548 | 0 | 0.0% | 0.0% |
| REJECT | GoodnessJSON/PiHole-Whitelist | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 270 | 52045 | 21 | 7.8% | 0.0% |
| REJECT | GoodnessJSON/PiHole-Whitelist | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 270 | 48729 | 12 | 4.4% | 0.0% |
| REJECT | Isaaker/Spotify-AdsList | Johnshall/Shadowrocket-ADBlock-Rules-Forever | 155422 | 52060 | 4121 | 7.9% | 2.0% |
| REJECT | Isaaker/Spotify-AdsList | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | 155422 | 45081 | 4660 | 10.3% | 2.4% |
| REJECT | Isaaker/Spotify-AdsList | YanbingJiang/Shadowrocket_diy_rules | 155422 | 17028 | 2976 | 17.5% | 1.8% |
| REJECT | Isaaker/Spotify-AdsList | anudeepND/whitelist | 155422 | 267 | 90 | 33.7% | 0.1% |
| REJECT | Isaaker/Spotify-AdsList | badmojr/1Hosts | 155422 | 0 | 0 | 0.0% | 0.0% |
| REJECT | Isaaker/Spotify-AdsList | furkan-bayrak/lg-tv-blocklist | 155422 | 115 | 4 | 3.5% | 0.0% |
| REJECT | Isaaker/Spotify-AdsList | marco-acorte/antispam-it | 155422 | 346345 | 3 | 0.0% | 0.0% |
| REJECT | Isaaker/Spotify-AdsList | nthack/Shadowrocket-ADBlock-Rules-Easy | 155422 | 16125 | 2553 | 15.8% | 1.5% |
| REJECT | Isaaker/Spotify-AdsList | phishdestroy/destroylist | 155422 | 234548 | 10 | 0.0% | 0.0% |
| REJECT | Isaaker/Spotify-AdsList | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 155422 | 52045 | 4109 | 7.9% | 2.0% |
| REJECT | Isaaker/Spotify-AdsList | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 155422 | 48729 | 1880 | 3.9% | 0.9% |
| REJECT | Johnshall/Shadowrocket-ADBlock-Rules-Forever | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | 52060 | 45081 | 13797 | 30.6% | 16.6% |
| REJECT | Johnshall/Shadowrocket-ADBlock-Rules-Forever | YanbingJiang/Shadowrocket_diy_rules | 52060 | 17028 | 2450 | 14.4% | 3.7% |
| REJECT | Johnshall/Shadowrocket-ADBlock-Rules-Forever | anudeepND/whitelist | 52060 | 267 | 21 | 7.9% | 0.0% |
| REJECT | Johnshall/Shadowrocket-ADBlock-Rules-Forever | badmojr/1Hosts | 52060 | 0 | 0 | 0.0% | 0.0% |
| REJECT | Johnshall/Shadowrocket-ADBlock-Rules-Forever | furkan-bayrak/lg-tv-blocklist | 52060 | 115 | 3 | 2.6% | 0.0% |
| REJECT | Johnshall/Shadowrocket-ADBlock-Rules-Forever | marco-acorte/antispam-it | 52060 | 346345 | 2 | 0.0% | 0.0% |
| REJECT | Johnshall/Shadowrocket-ADBlock-Rules-Forever | nthack/Shadowrocket-ADBlock-Rules-Easy | 52060 | 16125 | 2250 | 14.0% | 3.4% |
| REJECT | Johnshall/Shadowrocket-ADBlock-Rules-Forever | phishdestroy/destroylist | 52060 | 234548 | 11 | 0.0% | 0.0% |
| REJECT | Johnshall/Shadowrocket-ADBlock-Rules-Forever | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 52060 | 52045 | 51992 | 99.9% | 99.8% |
| REJECT | Johnshall/Shadowrocket-ADBlock-Rules-Forever | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 52060 | 48729 | 48729 | 100.0% | 93.6% |
| REJECT | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | YanbingJiang/Shadowrocket_diy_rules | 45081 | 17028 | 2917 | 17.1% | 4.9% |
| REJECT | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | anudeepND/whitelist | 45081 | 267 | 21 | 7.9% | 0.0% |
| REJECT | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | badmojr/1Hosts | 45081 | 0 | 0 | 0.0% | 0.0% |
| REJECT | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | furkan-bayrak/lg-tv-blocklist | 45081 | 115 | 3 | 2.6% | 0.0% |
| REJECT | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | marco-acorte/antispam-it | 45081 | 346345 | 2 | 0.0% | 0.0% |
| REJECT | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | nthack/Shadowrocket-ADBlock-Rules-Easy | 45081 | 16125 | 2718 | 16.9% | 4.6% |
| REJECT | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | phishdestroy/destroylist | 45081 | 234548 | 9 | 0.0% | 0.0% |
| REJECT | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 45081 | 52045 | 13729 | 30.5% | 16.5% |
| REJECT | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 45081 | 48729 | 10825 | 24.0% | 13.0% |
| REJECT | YanbingJiang/Shadowrocket_diy_rules | anudeepND/whitelist | 17028 | 267 | 3 | 1.1% | 0.0% |
| REJECT | YanbingJiang/Shadowrocket_diy_rules | badmojr/1Hosts | 17028 | 0 | 0 | 0.0% | 0.0% |
| REJECT | YanbingJiang/Shadowrocket_diy_rules | furkan-bayrak/lg-tv-blocklist | 17028 | 115 | 0 | 0.0% | 0.0% |
| REJECT | YanbingJiang/Shadowrocket_diy_rules | marco-acorte/antispam-it | 17028 | 346345 | 0 | 0.0% | 0.0% |
| REJECT | YanbingJiang/Shadowrocket_diy_rules | nthack/Shadowrocket-ADBlock-Rules-Easy | 17028 | 16125 | 16125 | 100.0% | 94.7% |
| REJECT | YanbingJiang/Shadowrocket_diy_rules | phishdestroy/destroylist | 17028 | 234548 | 4 | 0.0% | 0.0% |
| REJECT | YanbingJiang/Shadowrocket_diy_rules | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 17028 | 52045 | 2446 | 14.4% | 3.7% |
| REJECT | YanbingJiang/Shadowrocket_diy_rules | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 17028 | 48729 | 2326 | 13.7% | 3.7% |
| REJECT | anudeepND/whitelist | badmojr/1Hosts | 267 | 0 | 0 | 0.0% | 0.0% |
| REJECT | anudeepND/whitelist | furkan-bayrak/lg-tv-blocklist | 267 | 115 | 0 | 0.0% | 0.0% |
| REJECT | anudeepND/whitelist | marco-acorte/antispam-it | 267 | 346345 | 0 | 0.0% | 0.0% |
| REJECT | anudeepND/whitelist | nthack/Shadowrocket-ADBlock-Rules-Easy | 267 | 16125 | 3 | 1.1% | 0.0% |
| REJECT | anudeepND/whitelist | phishdestroy/destroylist | 267 | 234548 | 0 | 0.0% | 0.0% |
| REJECT | anudeepND/whitelist | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 267 | 52045 | 21 | 7.9% | 0.0% |
| REJECT | anudeepND/whitelist | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 267 | 48729 | 12 | 4.5% | 0.0% |
| REJECT | badmojr/1Hosts | furkan-bayrak/lg-tv-blocklist | 0 | 115 | 0 | 0.0% | 0.0% |
| REJECT | badmojr/1Hosts | marco-acorte/antispam-it | 0 | 346345 | 0 | 0.0% | 0.0% |
| REJECT | badmojr/1Hosts | nthack/Shadowrocket-ADBlock-Rules-Easy | 0 | 16125 | 0 | 0.0% | 0.0% |
| REJECT | badmojr/1Hosts | phishdestroy/destroylist | 0 | 234548 | 0 | 0.0% | 0.0% |
| REJECT | badmojr/1Hosts | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 0 | 52045 | 0 | 0.0% | 0.0% |
| REJECT | badmojr/1Hosts | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 0 | 48729 | 0 | 0.0% | 0.0% |
| REJECT | furkan-bayrak/lg-tv-blocklist | marco-acorte/antispam-it | 115 | 346345 | 0 | 0.0% | 0.0% |
| REJECT | furkan-bayrak/lg-tv-blocklist | nthack/Shadowrocket-ADBlock-Rules-Easy | 115 | 16125 | 0 | 0.0% | 0.0% |
| REJECT | furkan-bayrak/lg-tv-blocklist | phishdestroy/destroylist | 115 | 234548 | 0 | 0.0% | 0.0% |
| REJECT | furkan-bayrak/lg-tv-blocklist | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 115 | 52045 | 3 | 2.6% | 0.0% |
| REJECT | furkan-bayrak/lg-tv-blocklist | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 115 | 48729 | 3 | 2.6% | 0.0% |
| REJECT | marco-acorte/antispam-it | nthack/Shadowrocket-ADBlock-Rules-Easy | 346345 | 16125 | 0 | 0.0% | 0.0% |
| REJECT | marco-acorte/antispam-it | phishdestroy/destroylist | 346345 | 234548 | 0 | 0.0% | 0.0% |
| REJECT | marco-acorte/antispam-it | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 346345 | 52045 | 2 | 0.0% | 0.0% |
| REJECT | marco-acorte/antispam-it | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 346345 | 48729 | 0 | 0.0% | 0.0% |
| REJECT | nthack/Shadowrocket-ADBlock-Rules-Easy | phishdestroy/destroylist | 16125 | 234548 | 2 | 0.0% | 0.0% |
| REJECT | nthack/Shadowrocket-ADBlock-Rules-Easy | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 16125 | 52045 | 2249 | 13.9% | 3.4% |
| REJECT | nthack/Shadowrocket-ADBlock-Rules-Easy | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 16125 | 48729 | 2230 | 13.8% | 3.6% |
| REJECT | phishdestroy/destroylist | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 234548 | 52045 | 11 | 0.0% | 0.0% |
| REJECT | phishdestroy/destroylist | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 234548 | 48729 | 10 | 0.0% | 0.0% |
| REJECT | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 52045 | 48729 | 48729 | 100.0% | 93.6% |

## Cross-policy contradictions

Detected domains appearing under more than one policy: **814**

- `01122200.com`: PROXY, REJECT
- `123movies.to`: PROXY, REJECT
- `1511.com`: PROXY, REJECT
- `1688.com`: DIRECT, PROXY
- `17k.com`: DIRECT, PROXY
- `192.com`: PROXY, REJECT
- `195239.com`: PROXY, REJECT
- `1drv.com`: PROXY, REJECT
- `1mobile.com`: PROXY, REJECT
- `1xbet.com`: PROXY, REJECT
- `21sextury.com`: PROXY, REJECT
- `24smile.org`: PROXY, REJECT
- `2mdn-cn.net`: DIRECT, REJECT
- `2mdn.net`: DIRECT, PROXY, REJECT
- `2o7.net`: PROXY, REJECT
- `466453.com`: PROXY, REJECT
- `4dsply.com`: DIRECT, REJECT
- `50bang.org`: DIRECT, REJECT
- `51.la`: DIRECT, REJECT
- `51yes.com`: DIRECT, REJECT
- `71edge.com`: DIRECT, PROXY
- `888poker.com`: PROXY, REJECT
- `991.com`: PROXY, REJECT
- `9gag.com`: DIRECT, PROXY
- `9ht.com`: DIRECT, PROXY
- `a.teads.tv`: PROXY, REJECT
- `aaaa5115.com`: PROXY, REJECT
- `abercrombie.com`: DIRECT, PROXY
- `acg.rip`: DIRECT, PROXY
- `ad-maven.com`: PROXY, REJECT
- `ad.12306.cn`: DIRECT, REJECT
- `adash.man.aliyuncs.com`: DIRECT, REJECT
- `adcdownload.apple.com.akadns.net`: DIRECT, PROXY
- `addthis.com`: DIRECT, REJECT
- `adexchangeprediction.com`: DIRECT, REJECT
- `adf.ly`: DIRECT, REJECT
- `adme-net.com`: PROXY, REJECT
- `admob-cn.com`: DIRECT, REJECT
- `admob.com`: PROXY, REJECT
- `adnetworkperformance.com`: PROXY, REJECT
- `adobe.com`: DIRECT, PROXY
- `adobedtm.com`: PROXY, REJECT
- `adplxmd.com`: PROXY, REJECT
- `ads-twitter.com`: PROXY, REJECT
- `ads.exoclick.com`: PROXY, REJECT
- `ads.google.com`: PROXY, REJECT
- `adsense.com`: PROXY, REJECT
- `adserverplus.com`: PROXY, REJECT
- `adserverpub.com`: PROXY, REJECT
- `adservice.google.com`: DIRECT, REJECT
- `adultfriendfinder.com`: PROXY, REJECT
- `adxvip.com`: DIRECT, REJECT
- `agora.io`: DIRECT, PROXY
- `ahcdn.com`: PROXY, REJECT
- `aikapool.com`: PROXY, REJECT
- `airbrake.io`: PROXY, REJECT
- `aixifan.com`: DIRECT, PROXY
- `akamaihd.net`: PROXY, REJECT
- `akamaized.net`: PROXY, REJECT
- `ali213.net`: DIRECT, PROXY
- `alimama.com`: DIRECT, REJECT
- `aliyun.com`: DIRECT, PROXY
- `allyes.com`: DIRECT, REJECT
- `amazon-adsystem.com`: PROXY, REJECT
- `amazon.ca`: DIRECT, PROXY
- `amazon.co.uk`: DIRECT, PROXY
- `amazon.com`: DIRECT, PROXY
- `amazon.de`: DIRECT, PROXY
- `amazon.es`: DIRECT, PROXY
- `amazon.fr`: DIRECT, PROXY
- `amazon.in`: DIRECT, PROXY
- `amazon.it`: DIRECT, PROXY
- `amazonaws.com`: DIRECT, PROXY, REJECT
- `ameblo.jp`: DIRECT, PROXY
- `amp-api.podcasts.apple.com`: DIRECT, PROXY
- `amplitude.com`: PROXY, REJECT
- `analytics.strava.com`: DIRECT, REJECT
- `analytics.tiktok.com`: DIRECT, REJECT
- `animeidhentai.com`: PROXY, REJECT
- `anonfilesnew.com`: PROXY, REJECT
- `anquan.org`: DIRECT, REJECT
- `antpool.com`: PROXY, REJECT
- `anyporn.com`: PROXY, REJECT
- `aol.com`: DIRECT, PROXY
- `api.amplitude.com`: PROXY, REJECT
- `api.ettoday.net`: PROXY, REJECT
- `api.foursquare.com`: PROXY, REJECT
- `api.mixpanel.com`: PROXY, REJECT
- `api.rlcdn.com`: PROXY, REJECT
- `api.segment.io`: PROXY, REJECT
- `api.share.baidu.com`: PROXY, REJECT
- `app-measurement.com`: DIRECT, PROXY, REJECT
- `app.adjust.com`: DIRECT, REJECT
- `app.appsflyer.com`: DIRECT, REJECT
- `appldnld.apple.com`: DIRECT, PROXY
- `appldnld.g.aaplimg.com`: DIRECT, PROXY
- `apple.comscoreresearch.com`: PROXY, REJECT
- `apps5.oingo.com`: DIRECT, REJECT
- `apptjmp.com`: PROXY, REJECT
- `ar.hao123.com`: PROXY, REJECT
- `artcomix.com`: PROXY, REJECT
- `asiafriendfinder.com`: PROXY, REJECT
- `aspnetcdn.com`: PROXY, REJECT
- `atdmt.com`: PROXY, REJECT
- `avg.com`: DIRECT, PROXY
- `avistaz.to`: DIRECT, PROXY
- `avito.ru`: DIRECT, PROXY
- `awstrack.me`: PROXY, REJECT
- `az416426.vo.msecnd.net`: PROXY, REJECT
- `babm.texthelp.com`: PROXY, REJECT
- `badoink.com`: PROXY, REJECT
- `bag.itunes.apple.com`: DIRECT, PROXY
- `baidustatic.com`: DIRECT, REJECT
- `baifendian.com`: DIRECT, REJECT
- `battle.net`: DIRECT, PROXY
- `bc.game`: PROXY, REJECT
- `beacons.gcp.gvt2.com`: DIRECT, REJECT
- `beacons.gvt2.com`: DIRECT, REJECT
- `behance.net`: DIRECT, PROXY
- `bestgore.com`: PROXY, REJECT
- `bestshockers.com`: PROXY, REJECT
- `bet365.com`: DIRECT, PROXY
- `biddingx.com`: DIRECT, REJECT
- `bidswitch.net`: PROXY, REJECT
- `biliapi.net`: DIRECT, PROXY
- `bilibili.com`: DIRECT, PROXY
- `bilivideo.com`: DIRECT, PROXY
- `bing.com`: DIRECT, PROXY
- `bit.do`: PROXY, REJECT
- `bitbucket.io`: PROXY, REJECT
- `bitcoin.cz`: PROXY, REJECT
- `bjcathay.com`: DIRECT, REJECT
- `bkrtx.com`: PROXY, REJECT
- `blankrefer.com`: PROXY, REJECT
- `blog.google`: DIRECT, PROXY
- `bongacams.com`: PROXY, REJECT
- `bongacams7.com`: PROXY, REJECT
- `bookofsex.com`: PROXY, REJECT
- `boomtrain.com`: PROXY, REJECT
- `bootstrap.upsight-api.com`: PROXY, REJECT
- `box.com`: DIRECT, PROXY
- `braze.com`: PROXY, REJECT
- `brightcove01.brightcove.com`: PROXY, REJECT
- `bugleczmoidgxo.com`: PROXY, REJECT
- `bukalapak.com`: DIRECT, PROXY
- `buy.com`: PROXY, REJECT
- `buzzfeed.com`: DIRECT, PROXY
- `bw.com`: PROXY, REJECT
- `bytedance.com`: DIRECT, REJECT
- `byteoversea.com`: PROXY, REJECT
- `c.admob.com`: DIRECT, REJECT
- `c.go-mpulse.net`: PROXY, REJECT
- `camdough.com`: PROXY, REJECT
- `cameraboys.com`: PROXY, REJECT
- `canva.com`: DIRECT, PROXY
- `capital.com`: PROXY, REJECT
- `cartoontube.com`: PROXY, REJECT
- `cdn.apple-mapkit.com`: DIRECT, PROXY
- `cdn.jsdelivr.net`: DIRECT, PROXY
- `cdn.moengage.com`: PROXY, REJECT
- `cdn.mxpnl.com`: PROXY, REJECT
- `cdn.segment.com`: PROXY, REJECT
- `cdp.cloud.unity3d.com`: PROXY, REJECT
- `cds-cdn.v.aaplimg.com`: DIRECT, PROXY
- `cds.apple.com.akadns.net`: DIRECT, PROXY
- `centanet.com`: DIRECT, PROXY
- `certified-toolbar.com`: PROXY, REJECT
- `cf.cdn.inmobi.com`: PROXY, REJECT
- `changelly.com`: PROXY, REJECT
- `chdbits.co`: DIRECT, PROXY
- `chickenkiller.com`: PROXY, REJECT
- `cl1-cdn.origin-apple.com.akadns.net`: DIRECT, PROXY
- `cl3-cdn.origin-apple.com.akadns.net`: DIRECT, PROXY
- `cl4-cdn.origin-apple.com.akadns.net`: DIRECT, PROXY
- `cl5-cdn.origin-apple.com.akadns.net`: DIRECT, PROXY
- `cleansite.us`: PROXY, REJECT
- `clickadilla.com`: PROXY, REJECT
- `clickpoint.com`: PROXY, REJECT
- `clickserve.cc-dt.com`: DIRECT, REJECT
- `clickserve.dartsearch.net`: DIRECT, REJECT
- `clicksgear.com`: DIRECT, PROXY, REJECT
- `clicksor.com`: PROXY, REJECT
- `clientflow.apple.com.akadns.net`: DIRECT, PROXY
- `cloudconfig.googleapis.com`: PROXY, REJECT
- `cnet.com`: DIRECT, PROXY
- `cnn.com`: DIRECT, PROXY
- `cnzz.com`: DIRECT, REJECT
- `coincheck.com`: PROXY, REJECT
- `coinone.co.kr`: PROXY, REJECT
- `configuration.apple.com`: DIRECT, PROXY
- `configuration.apple.com.akadns.net`: DIRECT, PROXY
- `connect.ok.ru`: PROXY, REJECT
- `connectivitycheck.android.com`: PROXY, REJECT
- `connectivitycheck.gstatic.com`: DIRECT, REJECT
- `content.mql5.com`: PROXY, REJECT
- `cpatrk.net`: DIRECT, REJECT
- `crashlytics.com`: PROXY, REJECT
- `crashlyticsreports-pa.googleapis.com`: DIRECT, REJECT
- `criteo.com`: PROXY, REJECT
- `crittercism.com`: PROXY, REJECT

## Publication boundary

This stage does not add sources to the active registry, does not approve domains, and does not alter the three rule sets. Two genuinely independent, verified publishers and all existing deterministic gates remain required.
