# Policy source overlap audit

This report compares normalized domain sets across discovered publisher feeds. It is informational only: overlap does not prove common ancestry, and low overlap does not prove independence.

- Feeds fetched: **196**
- Cross-policy conflict domains: **3497**

| Policy | Publisher A | Publisher B | A domains | B domains | Shared | Smaller-set overlap | Jaccard |
|---|---|---|---:|---:|---:|---:|---:|
| DIRECT | ACL4SSR/ACL4SSR | Clash-FX/cn-apps-direct-domains | 605 | 120 | 73 | 60.8% | 11.2% |
| DIRECT | ACL4SSR/ACL4SSR | Hackl0us/SS-Rule-Snippet | 605 | 139 | 101 | 72.7% | 15.7% |
| DIRECT | ACL4SSR/ACL4SSR | Jovanykoch/rules | 605 | 6772 | 439 | 72.6% | 6.3% |
| DIRECT | ACL4SSR/ACL4SSR | YanbingJiang/Shadowrocket_diy_rules | 605 | 408 | 37 | 9.1% | 3.8% |
| DIRECT | ACL4SSR/ACL4SSR | h2y/Shadowrocket-ADBlock-Rules | 605 | 325 | 35 | 10.8% | 3.9% |
| DIRECT | ACL4SSR/ACL4SSR | nthack/Shadowrocket-ADBlock-Rules-Easy | 605 | 325 | 35 | 10.8% | 3.9% |
| DIRECT | ACL4SSR/ACL4SSR | tickmao/Rules | 605 | 195 | 6 | 3.1% | 0.8% |
| DIRECT | ACL4SSR/ACL4SSR | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 605 | 325 | 35 | 10.8% | 3.9% |
| DIRECT | Clash-FX/cn-apps-direct-domains | Hackl0us/SS-Rule-Snippet | 120 | 139 | 29 | 24.2% | 12.6% |
| DIRECT | Clash-FX/cn-apps-direct-domains | Jovanykoch/rules | 120 | 6772 | 83 | 69.2% | 1.2% |
| DIRECT | Clash-FX/cn-apps-direct-domains | YanbingJiang/Shadowrocket_diy_rules | 120 | 408 | 13 | 10.8% | 2.5% |
| DIRECT | Clash-FX/cn-apps-direct-domains | h2y/Shadowrocket-ADBlock-Rules | 120 | 325 | 13 | 10.8% | 3.0% |
| DIRECT | Clash-FX/cn-apps-direct-domains | nthack/Shadowrocket-ADBlock-Rules-Easy | 120 | 325 | 13 | 10.8% | 3.0% |
| DIRECT | Clash-FX/cn-apps-direct-domains | tickmao/Rules | 120 | 195 | 1 | 0.8% | 0.3% |
| DIRECT | Clash-FX/cn-apps-direct-domains | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 120 | 325 | 13 | 10.8% | 3.0% |
| DIRECT | Hackl0us/SS-Rule-Snippet | Jovanykoch/rules | 139 | 6772 | 93 | 66.9% | 1.4% |
| DIRECT | Hackl0us/SS-Rule-Snippet | YanbingJiang/Shadowrocket_diy_rules | 139 | 408 | 23 | 16.5% | 4.4% |
| DIRECT | Hackl0us/SS-Rule-Snippet | h2y/Shadowrocket-ADBlock-Rules | 139 | 325 | 22 | 15.8% | 5.0% |
| DIRECT | Hackl0us/SS-Rule-Snippet | nthack/Shadowrocket-ADBlock-Rules-Easy | 139 | 325 | 22 | 15.8% | 5.0% |
| DIRECT | Hackl0us/SS-Rule-Snippet | tickmao/Rules | 139 | 195 | 16 | 11.5% | 5.0% |
| DIRECT | Hackl0us/SS-Rule-Snippet | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 139 | 325 | 22 | 15.8% | 5.0% |
| DIRECT | Jovanykoch/rules | YanbingJiang/Shadowrocket_diy_rules | 6772 | 408 | 50 | 12.3% | 0.7% |
| DIRECT | Jovanykoch/rules | h2y/Shadowrocket-ADBlock-Rules | 6772 | 325 | 42 | 12.9% | 0.6% |
| DIRECT | Jovanykoch/rules | nthack/Shadowrocket-ADBlock-Rules-Easy | 6772 | 325 | 42 | 12.9% | 0.6% |
| DIRECT | Jovanykoch/rules | tickmao/Rules | 6772 | 195 | 16 | 8.2% | 0.2% |
| DIRECT | Jovanykoch/rules | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 6772 | 325 | 42 | 12.9% | 0.6% |
| DIRECT | YanbingJiang/Shadowrocket_diy_rules | h2y/Shadowrocket-ADBlock-Rules | 408 | 325 | 325 | 100.0% | 79.7% |
| DIRECT | YanbingJiang/Shadowrocket_diy_rules | nthack/Shadowrocket-ADBlock-Rules-Easy | 408 | 325 | 325 | 100.0% | 79.7% |
| DIRECT | YanbingJiang/Shadowrocket_diy_rules | tickmao/Rules | 408 | 195 | 58 | 29.7% | 10.6% |
| DIRECT | YanbingJiang/Shadowrocket_diy_rules | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 408 | 325 | 325 | 100.0% | 79.7% |
| DIRECT | h2y/Shadowrocket-ADBlock-Rules | nthack/Shadowrocket-ADBlock-Rules-Easy | 325 | 325 | 325 | 100.0% | 100.0% |
| DIRECT | h2y/Shadowrocket-ADBlock-Rules | tickmao/Rules | 325 | 195 | 1 | 0.5% | 0.2% |
| DIRECT | h2y/Shadowrocket-ADBlock-Rules | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 325 | 325 | 325 | 100.0% | 100.0% |
| DIRECT | nthack/Shadowrocket-ADBlock-Rules-Easy | tickmao/Rules | 325 | 195 | 1 | 0.5% | 0.2% |
| DIRECT | nthack/Shadowrocket-ADBlock-Rules-Easy | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 325 | 325 | 325 | 100.0% | 100.0% |
| DIRECT | tickmao/Rules | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 195 | 325 | 1 | 0.5% | 0.2% |
| PROXY | ACL4SSR/ACL4SSR | Hackl0us/SS-Rule-Snippet | 6816 | 493 | 339 | 68.8% | 4.9% |
| PROXY | ACL4SSR/ACL4SSR | Johnshall/Shadowrocket-ADBlock-Rules-Forever | 6816 | 30183 | 4622 | 67.8% | 14.3% |
| PROXY | ACL4SSR/ACL4SSR | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | 6816 | 39456 | 5627 | 82.6% | 13.8% |
| PROXY | ACL4SSR/ACL4SSR | YanbingJiang/Shadowrocket_diy_rules | 6816 | 5815 | 5156 | 88.7% | 69.0% |
| PROXY | ACL4SSR/ACL4SSR | gatework/surge-rules | 6816 | 4452 | 3787 | 85.1% | 50.6% |
| PROXY | ACL4SSR/ACL4SSR | h2y/Shadowrocket-ADBlock-Rules | 6816 | 5575 | 5040 | 90.4% | 68.6% |
| PROXY | ACL4SSR/ACL4SSR | ignaciocastro/a-dove-is-dumb | 6816 | 7606 | 0 | 0.0% | 0.0% |
| PROXY | ACL4SSR/ACL4SSR | nthack/Shadowrocket-ADBlock-Rules-Easy | 6816 | 5575 | 5040 | 90.4% | 68.6% |
| PROXY | ACL4SSR/ACL4SSR | sve1r/Rules-For-Quantumult-X | 6816 | 812 | 371 | 45.7% | 5.1% |
| PROXY | ACL4SSR/ACL4SSR | tickmao/Rules | 6816 | 7367 | 6644 | 97.5% | 88.1% |
| PROXY | ACL4SSR/ACL4SSR | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 6816 | 30166 | 4619 | 67.8% | 14.3% |
| PROXY | ACL4SSR/ACL4SSR | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 6816 | 4426 | 3795 | 85.7% | 51.0% |
| PROXY | Hackl0us/SS-Rule-Snippet | Johnshall/Shadowrocket-ADBlock-Rules-Forever | 493 | 30183 | 278 | 56.4% | 0.9% |
| PROXY | Hackl0us/SS-Rule-Snippet | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | 493 | 39456 | 301 | 61.1% | 0.8% |
| PROXY | Hackl0us/SS-Rule-Snippet | YanbingJiang/Shadowrocket_diy_rules | 493 | 5815 | 284 | 57.6% | 4.7% |
| PROXY | Hackl0us/SS-Rule-Snippet | gatework/surge-rules | 493 | 4452 | 226 | 45.8% | 4.8% |
| PROXY | Hackl0us/SS-Rule-Snippet | h2y/Shadowrocket-ADBlock-Rules | 493 | 5575 | 270 | 54.8% | 4.7% |
| PROXY | Hackl0us/SS-Rule-Snippet | ignaciocastro/a-dove-is-dumb | 493 | 7606 | 0 | 0.0% | 0.0% |
| PROXY | Hackl0us/SS-Rule-Snippet | nthack/Shadowrocket-ADBlock-Rules-Easy | 493 | 5575 | 270 | 54.8% | 4.7% |
| PROXY | Hackl0us/SS-Rule-Snippet | sve1r/Rules-For-Quantumult-X | 493 | 812 | 453 | 91.9% | 53.2% |
| PROXY | Hackl0us/SS-Rule-Snippet | tickmao/Rules | 493 | 7367 | 464 | 94.1% | 6.3% |
| PROXY | Hackl0us/SS-Rule-Snippet | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 493 | 30166 | 275 | 55.8% | 0.9% |
| PROXY | Hackl0us/SS-Rule-Snippet | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 493 | 4426 | 229 | 46.5% | 4.9% |
| PROXY | Johnshall/Shadowrocket-ADBlock-Rules-Forever | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | 30183 | 39456 | 20987 | 69.5% | 43.1% |
| PROXY | Johnshall/Shadowrocket-ADBlock-Rules-Forever | YanbingJiang/Shadowrocket_diy_rules | 30183 | 5815 | 3739 | 64.3% | 11.6% |
| PROXY | Johnshall/Shadowrocket-ADBlock-Rules-Forever | gatework/surge-rules | 30183 | 4452 | 4420 | 99.3% | 14.6% |
| PROXY | Johnshall/Shadowrocket-ADBlock-Rules-Forever | h2y/Shadowrocket-ADBlock-Rules | 30183 | 5575 | 3619 | 64.9% | 11.3% |
| PROXY | Johnshall/Shadowrocket-ADBlock-Rules-Forever | ignaciocastro/a-dove-is-dumb | 30183 | 7606 | 0 | 0.0% | 0.0% |
| PROXY | Johnshall/Shadowrocket-ADBlock-Rules-Forever | nthack/Shadowrocket-ADBlock-Rules-Easy | 30183 | 5575 | 3619 | 64.9% | 11.3% |
| PROXY | Johnshall/Shadowrocket-ADBlock-Rules-Forever | sve1r/Rules-For-Quantumult-X | 30183 | 812 | 300 | 36.9% | 1.0% |
| PROXY | Johnshall/Shadowrocket-ADBlock-Rules-Forever | tickmao/Rules | 30183 | 7367 | 4934 | 67.0% | 15.1% |
| PROXY | Johnshall/Shadowrocket-ADBlock-Rules-Forever | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 30183 | 30166 | 30161 | 100.0% | 99.9% |
| PROXY | Johnshall/Shadowrocket-ADBlock-Rules-Forever | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 30183 | 4426 | 4402 | 99.5% | 14.6% |
| PROXY | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | YanbingJiang/Shadowrocket_diy_rules | 39456 | 5815 | 4945 | 85.0% | 12.3% |
| PROXY | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | gatework/surge-rules | 39456 | 4452 | 4116 | 92.5% | 10.3% |
| PROXY | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | h2y/Shadowrocket-ADBlock-Rules | 39456 | 5575 | 4820 | 86.5% | 12.0% |
| PROXY | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | ignaciocastro/a-dove-is-dumb | 39456 | 7606 | 0 | 0.0% | 0.0% |
| PROXY | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | nthack/Shadowrocket-ADBlock-Rules-Easy | 39456 | 5575 | 4820 | 86.5% | 12.0% |
| PROXY | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | sve1r/Rules-For-Quantumult-X | 39456 | 812 | 324 | 39.9% | 0.8% |
| PROXY | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | tickmao/Rules | 39456 | 7367 | 5717 | 77.6% | 13.9% |
| PROXY | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 39456 | 30166 | 20966 | 69.5% | 43.1% |
| PROXY | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 39456 | 4426 | 4101 | 92.7% | 10.3% |
| PROXY | YanbingJiang/Shadowrocket_diy_rules | gatework/surge-rules | 5815 | 4452 | 2913 | 65.4% | 39.6% |
| PROXY | YanbingJiang/Shadowrocket_diy_rules | h2y/Shadowrocket-ADBlock-Rules | 5815 | 5575 | 5575 | 100.0% | 95.9% |
| PROXY | YanbingJiang/Shadowrocket_diy_rules | ignaciocastro/a-dove-is-dumb | 5815 | 7606 | 0 | 0.0% | 0.0% |
| PROXY | YanbingJiang/Shadowrocket_diy_rules | nthack/Shadowrocket-ADBlock-Rules-Easy | 5815 | 5575 | 5575 | 100.0% | 95.9% |
| PROXY | YanbingJiang/Shadowrocket_diy_rules | sve1r/Rules-For-Quantumult-X | 5815 | 812 | 313 | 38.5% | 5.0% |
| PROXY | YanbingJiang/Shadowrocket_diy_rules | tickmao/Rules | 5815 | 7367 | 5055 | 86.9% | 62.2% |
| PROXY | YanbingJiang/Shadowrocket_diy_rules | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 5815 | 30166 | 3739 | 64.3% | 11.6% |
| PROXY | YanbingJiang/Shadowrocket_diy_rules | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 5815 | 4426 | 2945 | 66.5% | 40.4% |
| PROXY | gatework/surge-rules | h2y/Shadowrocket-ADBlock-Rules | 4452 | 5575 | 2816 | 63.3% | 39.1% |
| PROXY | gatework/surge-rules | ignaciocastro/a-dove-is-dumb | 4452 | 7606 | 0 | 0.0% | 0.0% |
| PROXY | gatework/surge-rules | nthack/Shadowrocket-ADBlock-Rules-Easy | 4452 | 5575 | 2816 | 63.3% | 39.1% |
| PROXY | gatework/surge-rules | sve1r/Rules-For-Quantumult-X | 4452 | 812 | 248 | 30.5% | 4.9% |
| PROXY | gatework/surge-rules | tickmao/Rules | 4452 | 7367 | 4132 | 92.8% | 53.8% |
| PROXY | gatework/surge-rules | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 4452 | 30166 | 4420 | 99.3% | 14.6% |
| PROXY | gatework/surge-rules | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 4452 | 4426 | 4391 | 99.2% | 97.9% |
| PROXY | h2y/Shadowrocket-ADBlock-Rules | ignaciocastro/a-dove-is-dumb | 5575 | 7606 | 0 | 0.0% | 0.0% |
| PROXY | h2y/Shadowrocket-ADBlock-Rules | nthack/Shadowrocket-ADBlock-Rules-Easy | 5575 | 5575 | 5575 | 100.0% | 100.0% |
| PROXY | h2y/Shadowrocket-ADBlock-Rules | sve1r/Rules-For-Quantumult-X | 5575 | 812 | 286 | 35.2% | 4.7% |
| PROXY | h2y/Shadowrocket-ADBlock-Rules | tickmao/Rules | 5575 | 7367 | 4938 | 88.6% | 61.7% |
| PROXY | h2y/Shadowrocket-ADBlock-Rules | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 5575 | 30166 | 3620 | 64.9% | 11.3% |
| PROXY | h2y/Shadowrocket-ADBlock-Rules | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 5575 | 4426 | 2848 | 64.3% | 39.8% |
| PROXY | ignaciocastro/a-dove-is-dumb | nthack/Shadowrocket-ADBlock-Rules-Easy | 7606 | 5575 | 0 | 0.0% | 0.0% |
| PROXY | ignaciocastro/a-dove-is-dumb | sve1r/Rules-For-Quantumult-X | 7606 | 812 | 1 | 0.1% | 0.0% |
| PROXY | ignaciocastro/a-dove-is-dumb | tickmao/Rules | 7606 | 7367 | 0 | 0.0% | 0.0% |
| PROXY | ignaciocastro/a-dove-is-dumb | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 7606 | 30166 | 0 | 0.0% | 0.0% |
| PROXY | ignaciocastro/a-dove-is-dumb | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 7606 | 4426 | 0 | 0.0% | 0.0% |
| PROXY | nthack/Shadowrocket-ADBlock-Rules-Easy | sve1r/Rules-For-Quantumult-X | 5575 | 812 | 286 | 35.2% | 4.7% |
| PROXY | nthack/Shadowrocket-ADBlock-Rules-Easy | tickmao/Rules | 5575 | 7367 | 4938 | 88.6% | 61.7% |
| PROXY | nthack/Shadowrocket-ADBlock-Rules-Easy | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 5575 | 30166 | 3620 | 64.9% | 11.3% |
| PROXY | nthack/Shadowrocket-ADBlock-Rules-Easy | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 5575 | 4426 | 2848 | 64.3% | 39.8% |
| PROXY | sve1r/Rules-For-Quantumult-X | tickmao/Rules | 812 | 7367 | 536 | 66.0% | 7.0% |
| PROXY | sve1r/Rules-For-Quantumult-X | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 812 | 30166 | 297 | 36.6% | 1.0% |
| PROXY | sve1r/Rules-For-Quantumult-X | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 812 | 4426 | 250 | 30.8% | 5.0% |
| PROXY | tickmao/Rules | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 7367 | 30166 | 4928 | 66.9% | 15.1% |
| PROXY | tickmao/Rules | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 7367 | 4426 | 4086 | 92.3% | 53.0% |
| PROXY | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 30166 | 4426 | 4402 | 99.5% | 14.6% |
| REJECT | GoodnessJSON/PiHole-Whitelist | Hackl0us/SS-Rule-Snippet | 270 | 580 | 1 | 0.4% | 0.1% |
| REJECT | GoodnessJSON/PiHole-Whitelist | Isaaker/Spotify-AdsList | 270 | 155422 | 90 | 33.3% | 0.1% |
| REJECT | GoodnessJSON/PiHole-Whitelist | Johnshall/Shadowrocket-ADBlock-Rules-Forever | 270 | 53127 | 21 | 7.8% | 0.0% |
| REJECT | GoodnessJSON/PiHole-Whitelist | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | 270 | 45081 | 21 | 7.8% | 0.0% |
| REJECT | GoodnessJSON/PiHole-Whitelist | TG-Twilight/AWAvenue-Ads-Rule | 270 | 969 | 1 | 0.4% | 0.1% |
| REJECT | GoodnessJSON/PiHole-Whitelist | YanbingJiang/Shadowrocket_diy_rules | 270 | 17028 | 3 | 1.1% | 0.0% |
| REJECT | GoodnessJSON/PiHole-Whitelist | anudeepND/whitelist | 270 | 267 | 267 | 100.0% | 98.9% |
| REJECT | GoodnessJSON/PiHole-Whitelist | badmojr/1Hosts | 270 | 0 | 0 | 0.0% | 0.0% |
| REJECT | GoodnessJSON/PiHole-Whitelist | furkan-bayrak/lg-tv-blocklist | 270 | 115 | 0 | 0.0% | 0.0% |
| REJECT | GoodnessJSON/PiHole-Whitelist | h2y/Shadowrocket-ADBlock-Rules | 270 | 16125 | 3 | 1.1% | 0.0% |
| REJECT | GoodnessJSON/PiHole-Whitelist | hagezi/dns-blocklists | 270 | 681280 | 47 | 17.4% | 0.0% |
| REJECT | GoodnessJSON/PiHole-Whitelist | marco-acorte/antispam-it | 270 | 346345 | 0 | 0.0% | 0.0% |
| REJECT | GoodnessJSON/PiHole-Whitelist | nthack/Shadowrocket-ADBlock-Rules-Easy | 270 | 16125 | 3 | 1.1% | 0.0% |
| REJECT | GoodnessJSON/PiHole-Whitelist | pengelana/blocklist | 270 | 249406 | 2 | 0.7% | 0.0% |
| REJECT | GoodnessJSON/PiHole-Whitelist | phishdestroy/destroylist | 270 | 235834 | 0 | 0.0% | 0.0% |
| REJECT | GoodnessJSON/PiHole-Whitelist | sefinek/Sefinek-Blocklist-Collection | 270 | 81 | 0 | 0.0% | 0.0% |
| REJECT | GoodnessJSON/PiHole-Whitelist | sve1r/Rules-For-Quantumult-X | 270 | 106541 | 35 | 13.0% | 0.0% |
| REJECT | GoodnessJSON/PiHole-Whitelist | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 270 | 53119 | 21 | 7.8% | 0.0% |
| REJECT | GoodnessJSON/PiHole-Whitelist | zangadoprojets/pi-hole-blocklist | 270 | 57637 | 2 | 0.7% | 0.0% |
| REJECT | GoodnessJSON/PiHole-Whitelist | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 270 | 49793 | 12 | 4.4% | 0.0% |
| REJECT | Hackl0us/SS-Rule-Snippet | Isaaker/Spotify-AdsList | 580 | 155422 | 224 | 38.6% | 0.1% |
| REJECT | Hackl0us/SS-Rule-Snippet | Johnshall/Shadowrocket-ADBlock-Rules-Forever | 580 | 53127 | 183 | 31.6% | 0.3% |
| REJECT | Hackl0us/SS-Rule-Snippet | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | 580 | 45081 | 182 | 31.4% | 0.4% |
| REJECT | Hackl0us/SS-Rule-Snippet | TG-Twilight/AWAvenue-Ads-Rule | 580 | 969 | 27 | 4.7% | 1.8% |
| REJECT | Hackl0us/SS-Rule-Snippet | YanbingJiang/Shadowrocket_diy_rules | 580 | 17028 | 176 | 30.3% | 1.0% |
| REJECT | Hackl0us/SS-Rule-Snippet | anudeepND/whitelist | 580 | 267 | 1 | 0.4% | 0.1% |
| REJECT | Hackl0us/SS-Rule-Snippet | badmojr/1Hosts | 580 | 0 | 0 | 0.0% | 0.0% |
| REJECT | Hackl0us/SS-Rule-Snippet | furkan-bayrak/lg-tv-blocklist | 580 | 115 | 0 | 0.0% | 0.0% |
| REJECT | Hackl0us/SS-Rule-Snippet | h2y/Shadowrocket-ADBlock-Rules | 580 | 16125 | 137 | 23.6% | 0.8% |
| REJECT | Hackl0us/SS-Rule-Snippet | hagezi/dns-blocklists | 580 | 681280 | 231 | 39.8% | 0.0% |
| REJECT | Hackl0us/SS-Rule-Snippet | marco-acorte/antispam-it | 580 | 346345 | 0 | 0.0% | 0.0% |
| REJECT | Hackl0us/SS-Rule-Snippet | nthack/Shadowrocket-ADBlock-Rules-Easy | 580 | 16125 | 137 | 23.6% | 0.8% |
| REJECT | Hackl0us/SS-Rule-Snippet | pengelana/blocklist | 580 | 249406 | 45 | 7.8% | 0.0% |
| REJECT | Hackl0us/SS-Rule-Snippet | phishdestroy/destroylist | 580 | 235834 | 0 | 0.0% | 0.0% |
| REJECT | Hackl0us/SS-Rule-Snippet | sefinek/Sefinek-Blocklist-Collection | 580 | 81 | 0 | 0.0% | 0.0% |
| REJECT | Hackl0us/SS-Rule-Snippet | sve1r/Rules-For-Quantumult-X | 580 | 106541 | 511 | 88.1% | 0.5% |
| REJECT | Hackl0us/SS-Rule-Snippet | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 580 | 53119 | 136 | 23.4% | 0.3% |
| REJECT | Hackl0us/SS-Rule-Snippet | zangadoprojets/pi-hole-blocklist | 580 | 57637 | 0 | 0.0% | 0.0% |
| REJECT | Hackl0us/SS-Rule-Snippet | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 580 | 49793 | 101 | 17.4% | 0.2% |
| REJECT | Isaaker/Spotify-AdsList | Johnshall/Shadowrocket-ADBlock-Rules-Forever | 155422 | 53127 | 4122 | 7.8% | 2.0% |
| REJECT | Isaaker/Spotify-AdsList | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | 155422 | 45081 | 4660 | 10.3% | 2.4% |
| REJECT | Isaaker/Spotify-AdsList | TG-Twilight/AWAvenue-Ads-Rule | 155422 | 969 | 208 | 21.5% | 0.1% |
| REJECT | Isaaker/Spotify-AdsList | YanbingJiang/Shadowrocket_diy_rules | 155422 | 17028 | 2976 | 17.5% | 1.8% |
| REJECT | Isaaker/Spotify-AdsList | anudeepND/whitelist | 155422 | 267 | 90 | 33.7% | 0.1% |
| REJECT | Isaaker/Spotify-AdsList | badmojr/1Hosts | 155422 | 0 | 0 | 0.0% | 0.0% |
| REJECT | Isaaker/Spotify-AdsList | furkan-bayrak/lg-tv-blocklist | 155422 | 115 | 4 | 3.5% | 0.0% |
| REJECT | Isaaker/Spotify-AdsList | h2y/Shadowrocket-ADBlock-Rules | 155422 | 16125 | 2553 | 15.8% | 1.5% |
| REJECT | Isaaker/Spotify-AdsList | hagezi/dns-blocklists | 155422 | 681280 | 17403 | 11.2% | 2.1% |
| REJECT | Isaaker/Spotify-AdsList | marco-acorte/antispam-it | 155422 | 346345 | 3 | 0.0% | 0.0% |
| REJECT | Isaaker/Spotify-AdsList | nthack/Shadowrocket-ADBlock-Rules-Easy | 155422 | 16125 | 2553 | 15.8% | 1.5% |
| REJECT | Isaaker/Spotify-AdsList | pengelana/blocklist | 155422 | 249406 | 4021 | 2.6% | 1.0% |
| REJECT | Isaaker/Spotify-AdsList | phishdestroy/destroylist | 155422 | 235834 | 10 | 0.0% | 0.0% |
| REJECT | Isaaker/Spotify-AdsList | sefinek/Sefinek-Blocklist-Collection | 155422 | 81 | 0 | 0.0% | 0.0% |
| REJECT | Isaaker/Spotify-AdsList | sve1r/Rules-For-Quantumult-X | 155422 | 106541 | 9595 | 9.0% | 3.8% |
| REJECT | Isaaker/Spotify-AdsList | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 155422 | 53119 | 4110 | 7.7% | 2.0% |
| REJECT | Isaaker/Spotify-AdsList | zangadoprojets/pi-hole-blocklist | 155422 | 57637 | 18 | 0.0% | 0.0% |
| REJECT | Isaaker/Spotify-AdsList | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 155422 | 49793 | 1880 | 3.8% | 0.9% |
| REJECT | Johnshall/Shadowrocket-ADBlock-Rules-Forever | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | 53127 | 45081 | 13797 | 30.6% | 16.3% |
| REJECT | Johnshall/Shadowrocket-ADBlock-Rules-Forever | TG-Twilight/AWAvenue-Ads-Rule | 53127 | 969 | 64 | 6.6% | 0.1% |
| REJECT | Johnshall/Shadowrocket-ADBlock-Rules-Forever | YanbingJiang/Shadowrocket_diy_rules | 53127 | 17028 | 2450 | 14.4% | 3.6% |
| REJECT | Johnshall/Shadowrocket-ADBlock-Rules-Forever | anudeepND/whitelist | 53127 | 267 | 21 | 7.9% | 0.0% |
| REJECT | Johnshall/Shadowrocket-ADBlock-Rules-Forever | badmojr/1Hosts | 53127 | 0 | 0 | 0.0% | 0.0% |
| REJECT | Johnshall/Shadowrocket-ADBlock-Rules-Forever | furkan-bayrak/lg-tv-blocklist | 53127 | 115 | 3 | 2.6% | 0.0% |
| REJECT | Johnshall/Shadowrocket-ADBlock-Rules-Forever | h2y/Shadowrocket-ADBlock-Rules | 53127 | 16125 | 2250 | 14.0% | 3.4% |
| REJECT | Johnshall/Shadowrocket-ADBlock-Rules-Forever | hagezi/dns-blocklists | 53127 | 681280 | 50684 | 95.4% | 7.4% |
| REJECT | Johnshall/Shadowrocket-ADBlock-Rules-Forever | marco-acorte/antispam-it | 53127 | 346345 | 2 | 0.0% | 0.0% |
| REJECT | Johnshall/Shadowrocket-ADBlock-Rules-Forever | nthack/Shadowrocket-ADBlock-Rules-Easy | 53127 | 16125 | 2250 | 14.0% | 3.4% |
| REJECT | Johnshall/Shadowrocket-ADBlock-Rules-Forever | pengelana/blocklist | 53127 | 249406 | 41267 | 77.7% | 15.8% |
| REJECT | Johnshall/Shadowrocket-ADBlock-Rules-Forever | phishdestroy/destroylist | 53127 | 235834 | 11 | 0.0% | 0.0% |
| REJECT | Johnshall/Shadowrocket-ADBlock-Rules-Forever | sefinek/Sefinek-Blocklist-Collection | 53127 | 81 | 0 | 0.0% | 0.0% |
| REJECT | Johnshall/Shadowrocket-ADBlock-Rules-Forever | sve1r/Rules-For-Quantumult-X | 53127 | 106541 | 21928 | 41.3% | 15.9% |
| REJECT | Johnshall/Shadowrocket-ADBlock-Rules-Forever | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 53127 | 53119 | 53059 | 99.9% | 99.8% |
| REJECT | Johnshall/Shadowrocket-ADBlock-Rules-Forever | zangadoprojets/pi-hole-blocklist | 53127 | 57637 | 0 | 0.0% | 0.0% |
| REJECT | Johnshall/Shadowrocket-ADBlock-Rules-Forever | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 53127 | 49793 | 49793 | 100.0% | 93.7% |
| REJECT | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | TG-Twilight/AWAvenue-Ads-Rule | 45081 | 969 | 61 | 6.3% | 0.1% |
| REJECT | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | YanbingJiang/Shadowrocket_diy_rules | 45081 | 17028 | 2917 | 17.1% | 4.9% |
| REJECT | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | anudeepND/whitelist | 45081 | 267 | 21 | 7.9% | 0.0% |
| REJECT | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | badmojr/1Hosts | 45081 | 0 | 0 | 0.0% | 0.0% |
| REJECT | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | furkan-bayrak/lg-tv-blocklist | 45081 | 115 | 3 | 2.6% | 0.0% |
| REJECT | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | h2y/Shadowrocket-ADBlock-Rules | 45081 | 16125 | 2718 | 16.9% | 4.6% |
| REJECT | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | hagezi/dns-blocklists | 45081 | 681280 | 15546 | 34.5% | 2.2% |
| REJECT | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | marco-acorte/antispam-it | 45081 | 346345 | 2 | 0.0% | 0.0% |
| REJECT | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | nthack/Shadowrocket-ADBlock-Rules-Easy | 45081 | 16125 | 2718 | 16.9% | 4.6% |
| REJECT | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | pengelana/blocklist | 45081 | 249406 | 10850 | 24.1% | 3.8% |
| REJECT | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | phishdestroy/destroylist | 45081 | 235834 | 9 | 0.0% | 0.0% |
| REJECT | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | sefinek/Sefinek-Blocklist-Collection | 45081 | 81 | 0 | 0.0% | 0.0% |
| REJECT | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | sve1r/Rules-For-Quantumult-X | 45081 | 106541 | 22702 | 50.4% | 17.6% |
| REJECT | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 45081 | 53119 | 13729 | 30.5% | 16.3% |
| REJECT | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | zangadoprojets/pi-hole-blocklist | 45081 | 57637 | 0 | 0.0% | 0.0% |
| REJECT | NZNL31/Shadowrocket-Ad-DNS-Leak-Rules | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 45081 | 49793 | 10825 | 24.0% | 12.9% |
| REJECT | TG-Twilight/AWAvenue-Ads-Rule | YanbingJiang/Shadowrocket_diy_rules | 969 | 17028 | 96 | 9.9% | 0.5% |
| REJECT | TG-Twilight/AWAvenue-Ads-Rule | anudeepND/whitelist | 969 | 267 | 1 | 0.4% | 0.1% |
| REJECT | TG-Twilight/AWAvenue-Ads-Rule | badmojr/1Hosts | 969 | 0 | 0 | 0.0% | 0.0% |
| REJECT | TG-Twilight/AWAvenue-Ads-Rule | furkan-bayrak/lg-tv-blocklist | 969 | 115 | 0 | 0.0% | 0.0% |
| REJECT | TG-Twilight/AWAvenue-Ads-Rule | h2y/Shadowrocket-ADBlock-Rules | 969 | 16125 | 27 | 2.8% | 0.2% |
| REJECT | TG-Twilight/AWAvenue-Ads-Rule | hagezi/dns-blocklists | 969 | 681280 | 732 | 75.5% | 0.1% |
| REJECT | TG-Twilight/AWAvenue-Ads-Rule | marco-acorte/antispam-it | 969 | 346345 | 0 | 0.0% | 0.0% |
| REJECT | TG-Twilight/AWAvenue-Ads-Rule | nthack/Shadowrocket-ADBlock-Rules-Easy | 969 | 16125 | 27 | 2.8% | 0.2% |
| REJECT | TG-Twilight/AWAvenue-Ads-Rule | pengelana/blocklist | 969 | 249406 | 57 | 5.9% | 0.0% |
| REJECT | TG-Twilight/AWAvenue-Ads-Rule | phishdestroy/destroylist | 969 | 235834 | 0 | 0.0% | 0.0% |
| REJECT | TG-Twilight/AWAvenue-Ads-Rule | sefinek/Sefinek-Blocklist-Collection | 969 | 81 | 0 | 0.0% | 0.0% |
| REJECT | TG-Twilight/AWAvenue-Ads-Rule | sve1r/Rules-For-Quantumult-X | 969 | 106541 | 705 | 72.8% | 0.7% |
| REJECT | TG-Twilight/AWAvenue-Ads-Rule | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 969 | 53119 | 63 | 6.5% | 0.1% |
| REJECT | TG-Twilight/AWAvenue-Ads-Rule | zangadoprojets/pi-hole-blocklist | 969 | 57637 | 1 | 0.1% | 0.0% |
| REJECT | TG-Twilight/AWAvenue-Ads-Rule | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 969 | 49793 | 38 | 3.9% | 0.1% |
| REJECT | YanbingJiang/Shadowrocket_diy_rules | anudeepND/whitelist | 17028 | 267 | 3 | 1.1% | 0.0% |
| REJECT | YanbingJiang/Shadowrocket_diy_rules | badmojr/1Hosts | 17028 | 0 | 0 | 0.0% | 0.0% |
| REJECT | YanbingJiang/Shadowrocket_diy_rules | furkan-bayrak/lg-tv-blocklist | 17028 | 115 | 0 | 0.0% | 0.0% |
| REJECT | YanbingJiang/Shadowrocket_diy_rules | h2y/Shadowrocket-ADBlock-Rules | 17028 | 16125 | 16125 | 100.0% | 94.7% |
| REJECT | YanbingJiang/Shadowrocket_diy_rules | hagezi/dns-blocklists | 17028 | 681280 | 3186 | 18.7% | 0.5% |
| REJECT | YanbingJiang/Shadowrocket_diy_rules | marco-acorte/antispam-it | 17028 | 346345 | 0 | 0.0% | 0.0% |
| REJECT | YanbingJiang/Shadowrocket_diy_rules | nthack/Shadowrocket-ADBlock-Rules-Easy | 17028 | 16125 | 16125 | 100.0% | 94.7% |
| REJECT | YanbingJiang/Shadowrocket_diy_rules | pengelana/blocklist | 17028 | 249406 | 1490 | 8.8% | 0.6% |
| REJECT | YanbingJiang/Shadowrocket_diy_rules | phishdestroy/destroylist | 17028 | 235834 | 4 | 0.0% | 0.0% |
| REJECT | YanbingJiang/Shadowrocket_diy_rules | sefinek/Sefinek-Blocklist-Collection | 17028 | 81 | 0 | 0.0% | 0.0% |
| REJECT | YanbingJiang/Shadowrocket_diy_rules | sve1r/Rules-For-Quantumult-X | 17028 | 106541 | 4189 | 24.6% | 3.5% |
| REJECT | YanbingJiang/Shadowrocket_diy_rules | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 17028 | 53119 | 2446 | 14.4% | 3.6% |
| REJECT | YanbingJiang/Shadowrocket_diy_rules | zangadoprojets/pi-hole-blocklist | 17028 | 57637 | 0 | 0.0% | 0.0% |
| REJECT | YanbingJiang/Shadowrocket_diy_rules | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 17028 | 49793 | 2326 | 13.7% | 3.6% |
| REJECT | anudeepND/whitelist | badmojr/1Hosts | 267 | 0 | 0 | 0.0% | 0.0% |
| REJECT | anudeepND/whitelist | furkan-bayrak/lg-tv-blocklist | 267 | 115 | 0 | 0.0% | 0.0% |
| REJECT | anudeepND/whitelist | h2y/Shadowrocket-ADBlock-Rules | 267 | 16125 | 3 | 1.1% | 0.0% |
| REJECT | anudeepND/whitelist | hagezi/dns-blocklists | 267 | 681280 | 46 | 17.2% | 0.0% |
| REJECT | anudeepND/whitelist | marco-acorte/antispam-it | 267 | 346345 | 0 | 0.0% | 0.0% |
| REJECT | anudeepND/whitelist | nthack/Shadowrocket-ADBlock-Rules-Easy | 267 | 16125 | 3 | 1.1% | 0.0% |
| REJECT | anudeepND/whitelist | pengelana/blocklist | 267 | 249406 | 2 | 0.7% | 0.0% |
| REJECT | anudeepND/whitelist | phishdestroy/destroylist | 267 | 235834 | 0 | 0.0% | 0.0% |
| REJECT | anudeepND/whitelist | sefinek/Sefinek-Blocklist-Collection | 267 | 81 | 0 | 0.0% | 0.0% |
| REJECT | anudeepND/whitelist | sve1r/Rules-For-Quantumult-X | 267 | 106541 | 35 | 13.1% | 0.0% |
| REJECT | anudeepND/whitelist | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 267 | 53119 | 21 | 7.9% | 0.0% |
| REJECT | anudeepND/whitelist | zangadoprojets/pi-hole-blocklist | 267 | 57637 | 2 | 0.7% | 0.0% |
| REJECT | anudeepND/whitelist | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 267 | 49793 | 12 | 4.5% | 0.0% |
| REJECT | badmojr/1Hosts | furkan-bayrak/lg-tv-blocklist | 0 | 115 | 0 | 0.0% | 0.0% |
| REJECT | badmojr/1Hosts | h2y/Shadowrocket-ADBlock-Rules | 0 | 16125 | 0 | 0.0% | 0.0% |
| REJECT | badmojr/1Hosts | hagezi/dns-blocklists | 0 | 681280 | 0 | 0.0% | 0.0% |
| REJECT | badmojr/1Hosts | marco-acorte/antispam-it | 0 | 346345 | 0 | 0.0% | 0.0% |
| REJECT | badmojr/1Hosts | nthack/Shadowrocket-ADBlock-Rules-Easy | 0 | 16125 | 0 | 0.0% | 0.0% |
| REJECT | badmojr/1Hosts | pengelana/blocklist | 0 | 249406 | 0 | 0.0% | 0.0% |
| REJECT | badmojr/1Hosts | phishdestroy/destroylist | 0 | 235834 | 0 | 0.0% | 0.0% |
| REJECT | badmojr/1Hosts | sefinek/Sefinek-Blocklist-Collection | 0 | 81 | 0 | 0.0% | 0.0% |
| REJECT | badmojr/1Hosts | sve1r/Rules-For-Quantumult-X | 0 | 106541 | 0 | 0.0% | 0.0% |
| REJECT | badmojr/1Hosts | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 0 | 53119 | 0 | 0.0% | 0.0% |
| REJECT | badmojr/1Hosts | zangadoprojets/pi-hole-blocklist | 0 | 57637 | 0 | 0.0% | 0.0% |
| REJECT | badmojr/1Hosts | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 0 | 49793 | 0 | 0.0% | 0.0% |
| REJECT | furkan-bayrak/lg-tv-blocklist | h2y/Shadowrocket-ADBlock-Rules | 115 | 16125 | 0 | 0.0% | 0.0% |
| REJECT | furkan-bayrak/lg-tv-blocklist | hagezi/dns-blocklists | 115 | 681280 | 6 | 5.2% | 0.0% |
| REJECT | furkan-bayrak/lg-tv-blocklist | marco-acorte/antispam-it | 115 | 346345 | 0 | 0.0% | 0.0% |
| REJECT | furkan-bayrak/lg-tv-blocklist | nthack/Shadowrocket-ADBlock-Rules-Easy | 115 | 16125 | 0 | 0.0% | 0.0% |
| REJECT | furkan-bayrak/lg-tv-blocklist | pengelana/blocklist | 115 | 249406 | 1 | 0.9% | 0.0% |
| REJECT | furkan-bayrak/lg-tv-blocklist | phishdestroy/destroylist | 115 | 235834 | 0 | 0.0% | 0.0% |
| REJECT | furkan-bayrak/lg-tv-blocklist | sefinek/Sefinek-Blocklist-Collection | 115 | 81 | 0 | 0.0% | 0.0% |
| REJECT | furkan-bayrak/lg-tv-blocklist | sve1r/Rules-For-Quantumult-X | 115 | 106541 | 3 | 2.6% | 0.0% |
| REJECT | furkan-bayrak/lg-tv-blocklist | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 115 | 53119 | 3 | 2.6% | 0.0% |
| REJECT | furkan-bayrak/lg-tv-blocklist | zangadoprojets/pi-hole-blocklist | 115 | 57637 | 0 | 0.0% | 0.0% |
| REJECT | furkan-bayrak/lg-tv-blocklist | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 115 | 49793 | 3 | 2.6% | 0.0% |
| REJECT | h2y/Shadowrocket-ADBlock-Rules | hagezi/dns-blocklists | 16125 | 681280 | 2609 | 16.2% | 0.4% |
| REJECT | h2y/Shadowrocket-ADBlock-Rules | marco-acorte/antispam-it | 16125 | 346345 | 0 | 0.0% | 0.0% |
| REJECT | h2y/Shadowrocket-ADBlock-Rules | nthack/Shadowrocket-ADBlock-Rules-Easy | 16125 | 16125 | 16125 | 100.0% | 100.0% |
| REJECT | h2y/Shadowrocket-ADBlock-Rules | pengelana/blocklist | 16125 | 249406 | 1285 | 8.0% | 0.5% |
| REJECT | h2y/Shadowrocket-ADBlock-Rules | phishdestroy/destroylist | 16125 | 235834 | 2 | 0.0% | 0.0% |
| REJECT | h2y/Shadowrocket-ADBlock-Rules | sefinek/Sefinek-Blocklist-Collection | 16125 | 81 | 0 | 0.0% | 0.0% |
| REJECT | h2y/Shadowrocket-ADBlock-Rules | sve1r/Rules-For-Quantumult-X | 16125 | 106541 | 3575 | 22.2% | 3.0% |
| REJECT | h2y/Shadowrocket-ADBlock-Rules | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 16125 | 53119 | 2249 | 13.9% | 3.4% |
| REJECT | h2y/Shadowrocket-ADBlock-Rules | zangadoprojets/pi-hole-blocklist | 16125 | 57637 | 0 | 0.0% | 0.0% |
| REJECT | h2y/Shadowrocket-ADBlock-Rules | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 16125 | 49793 | 2230 | 13.8% | 3.5% |
| REJECT | hagezi/dns-blocklists | marco-acorte/antispam-it | 681280 | 346345 | 56 | 0.0% | 0.0% |
| REJECT | hagezi/dns-blocklists | nthack/Shadowrocket-ADBlock-Rules-Easy | 681280 | 16125 | 2609 | 16.2% | 0.4% |
| REJECT | hagezi/dns-blocklists | pengelana/blocklist | 681280 | 249406 | 167626 | 67.2% | 22.0% |
| REJECT | hagezi/dns-blocklists | phishdestroy/destroylist | 681280 | 235834 | 9832 | 4.2% | 1.1% |
| REJECT | hagezi/dns-blocklists | sefinek/Sefinek-Blocklist-Collection | 681280 | 81 | 2 | 2.5% | 0.0% |
| REJECT | hagezi/dns-blocklists | sve1r/Rules-For-Quantumult-X | 681280 | 106541 | 41421 | 38.9% | 5.5% |
| REJECT | hagezi/dns-blocklists | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 681280 | 53119 | 50678 | 95.4% | 7.4% |
| REJECT | hagezi/dns-blocklists | zangadoprojets/pi-hole-blocklist | 681280 | 57637 | 176 | 0.3% | 0.0% |
| REJECT | hagezi/dns-blocklists | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 681280 | 49793 | 47775 | 95.9% | 7.0% |
| REJECT | marco-acorte/antispam-it | nthack/Shadowrocket-ADBlock-Rules-Easy | 346345 | 16125 | 0 | 0.0% | 0.0% |
| REJECT | marco-acorte/antispam-it | pengelana/blocklist | 346345 | 249406 | 3 | 0.0% | 0.0% |
| REJECT | marco-acorte/antispam-it | phishdestroy/destroylist | 346345 | 235834 | 0 | 0.0% | 0.0% |
| REJECT | marco-acorte/antispam-it | sefinek/Sefinek-Blocklist-Collection | 346345 | 81 | 0 | 0.0% | 0.0% |
| REJECT | marco-acorte/antispam-it | sve1r/Rules-For-Quantumult-X | 346345 | 106541 | 1 | 0.0% | 0.0% |
| REJECT | marco-acorte/antispam-it | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 346345 | 53119 | 2 | 0.0% | 0.0% |
| REJECT | marco-acorte/antispam-it | zangadoprojets/pi-hole-blocklist | 346345 | 57637 | 0 | 0.0% | 0.0% |
| REJECT | marco-acorte/antispam-it | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 346345 | 49793 | 0 | 0.0% | 0.0% |
| REJECT | nthack/Shadowrocket-ADBlock-Rules-Easy | pengelana/blocklist | 16125 | 249406 | 1285 | 8.0% | 0.5% |
| REJECT | nthack/Shadowrocket-ADBlock-Rules-Easy | phishdestroy/destroylist | 16125 | 235834 | 2 | 0.0% | 0.0% |
| REJECT | nthack/Shadowrocket-ADBlock-Rules-Easy | sefinek/Sefinek-Blocklist-Collection | 16125 | 81 | 0 | 0.0% | 0.0% |
| REJECT | nthack/Shadowrocket-ADBlock-Rules-Easy | sve1r/Rules-For-Quantumult-X | 16125 | 106541 | 3575 | 22.2% | 3.0% |
| REJECT | nthack/Shadowrocket-ADBlock-Rules-Easy | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 16125 | 53119 | 2249 | 13.9% | 3.4% |
| REJECT | nthack/Shadowrocket-ADBlock-Rules-Easy | zangadoprojets/pi-hole-blocklist | 16125 | 57637 | 0 | 0.0% | 0.0% |
| REJECT | nthack/Shadowrocket-ADBlock-Rules-Easy | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 16125 | 49793 | 2230 | 13.8% | 3.5% |
| REJECT | pengelana/blocklist | phishdestroy/destroylist | 249406 | 235834 | 11865 | 5.0% | 2.5% |
| REJECT | pengelana/blocklist | sefinek/Sefinek-Blocklist-Collection | 249406 | 81 | 0 | 0.0% | 0.0% |
| REJECT | pengelana/blocklist | sve1r/Rules-For-Quantumult-X | 249406 | 106541 | 20403 | 19.2% | 6.1% |
| REJECT | pengelana/blocklist | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 249406 | 53119 | 41268 | 77.7% | 15.8% |
| REJECT | pengelana/blocklist | zangadoprojets/pi-hole-blocklist | 249406 | 57637 | 1 | 0.0% | 0.0% |
| REJECT | pengelana/blocklist | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 249406 | 49793 | 40743 | 81.8% | 15.8% |
| REJECT | phishdestroy/destroylist | sefinek/Sefinek-Blocklist-Collection | 235834 | 81 | 1 | 1.2% | 0.0% |
| REJECT | phishdestroy/destroylist | sve1r/Rules-For-Quantumult-X | 235834 | 106541 | 13 | 0.0% | 0.0% |
| REJECT | phishdestroy/destroylist | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 235834 | 53119 | 11 | 0.0% | 0.0% |
| REJECT | phishdestroy/destroylist | zangadoprojets/pi-hole-blocklist | 235834 | 57637 | 0 | 0.0% | 0.0% |
| REJECT | phishdestroy/destroylist | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 235834 | 49793 | 10 | 0.0% | 0.0% |
| REJECT | sefinek/Sefinek-Blocklist-Collection | sve1r/Rules-For-Quantumult-X | 81 | 106541 | 0 | 0.0% | 0.0% |
| REJECT | sefinek/Sefinek-Blocklist-Collection | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 81 | 53119 | 0 | 0.0% | 0.0% |
| REJECT | sefinek/Sefinek-Blocklist-Collection | zangadoprojets/pi-hole-blocklist | 81 | 57637 | 0 | 0.0% | 0.0% |
| REJECT | sefinek/Sefinek-Blocklist-Collection | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 81 | 49793 | 0 | 0.0% | 0.0% |
| REJECT | sve1r/Rules-For-Quantumult-X | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | 106541 | 53119 | 21874 | 41.2% | 15.9% |
| REJECT | sve1r/Rules-For-Quantumult-X | zangadoprojets/pi-hole-blocklist | 106541 | 57637 | 10 | 0.0% | 0.0% |
| REJECT | sve1r/Rules-For-Quantumult-X | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 106541 | 49793 | 20625 | 41.4% | 15.2% |
| REJECT | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | zangadoprojets/pi-hole-blocklist | 53119 | 57637 | 0 | 0.0% | 0.0% |
| REJECT | tumblemelon/Shadowrocket-ADBlock-Rules-Forever | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 53119 | 49793 | 49793 | 100.0% | 93.7% |
| REJECT | zangadoprojets/pi-hole-blocklist | zhouzhouprogram/Shadowrocket-ADBlock-Rules | 57637 | 49793 | 0 | 0.0% | 0.0% |

## Cross-policy contradictions

Detected domains appearing under more than one policy: **3497**

- `000webhost.com`: PROXY, REJECT
- `01122200.com`: PROXY, REJECT
- `08lkk.com`: PROXY, REJECT
- `09061.com`: PROXY, REJECT
- `0mag.net`: PROXY, REJECT
- `0rz.tw`: PROXY, REJECT
- `0youtube.com`: PROXY, REJECT
- `1000giri.net`: PROXY, REJECT
- `100mountain.com`: PROXY, REJECT
- `101010.pl`: PROXY, REJECT
- `1024huijia.com`: PROXY, REJECT
- `10bet.com`: PROXY, REJECT
- `118book.com`: PROXY, REJECT
- `1234.as`: PROXY, REJECT
- `123juzi.net`: DIRECT, REJECT
- `123movies.to`: PROXY, REJECT
- `126.net`: DIRECT, PROXY
- `127.net`: DIRECT, PROXY
- `12bet.com`: PROXY, REJECT
- `12vpx.com`: PROXY, REJECT
- `12wo.com`: PROXY, REJECT
- `1337.cx`: PROXY, REJECT
- `1337x.is`: PROXY, REJECT
- `1337x.to`: PROXY, REJECT
- `138.com`: PROXY, REJECT
- `141545.com`: PROXY, REJECT
- `141jav.com`: PROXY, REJECT
- `1511.com`: PROXY, REJECT
- `155game.com`: PROXY, REJECT
- `163.com`: DIRECT, PROXY
- `163yun.com`: DIRECT, PROXY
- `1680180.com`: PROXY, REJECT
- `1688.com`: DIRECT, PROXY
- `17k.com`: DIRECT, PROXY
- `18avtube.com`: PROXY, REJECT
- `18comic.fun`: PROXY, REJECT
- `18comic1.art`: PROXY, REJECT
- `18comic2.art`: PROXY, REJECT
- `192.com`: PROXY, REJECT
- `195239.com`: PROXY, REJECT
- `198game.com`: PROXY, REJECT
- `19yxw.com`: DIRECT, REJECT
- `1drv.com`: PROXY, REJECT
- `1dumb.com`: PROXY, REJECT
- `1mobile.com`: PROXY, REJECT
- `1proxy.de`: PROXY, REJECT
- `1ting.com`: DIRECT, REJECT
- `1vpn.org`: PROXY, REJECT
- `1worldonline.com`: PROXY, REJECT
- `1xbet.com`: PROXY, REJECT
- `2049bbs.xyz`: PROXY, REJECT
- `21sextury.com`: PROXY, REJECT
- `2345.cc`: DIRECT, REJECT
- `2345.com`: DIRECT, REJECT
- `24smile.org`: PROXY, REJECT
- `25u.com`: PROXY, REJECT
- `265.com`: DIRECT, REJECT
- `2mdn-cn.net`: DIRECT, REJECT
- `2mdn.net`: DIRECT, PROXY, REJECT
- `2miners.com`: PROXY, REJECT
- `2o7.net`: PROXY, REJECT
- `2proxy.de`: PROXY, REJECT
- `2waky.com`: PROXY, REJECT
- `3-a.net`: PROXY, REJECT
- `3004ss.vip`: PROXY, REJECT
- `32red.com`: PROXY, REJECT
- `3322.org`: DIRECT, REJECT
- `360buyimg.com`: DIRECT, PROXY
- `360chou.com`: DIRECT, REJECT
- `360kuai.com`: DIRECT, REJECT
- `360os.com`: DIRECT, REJECT
- `365dmp.com`: DIRECT, REJECT
- `36dm.com`: PROXY, REJECT
- `36kr.com`: DIRECT, PROXY
- `3bmmavpm.life`: PROXY, REJECT
- `3dmgame.com`: DIRECT, REJECT
- `3dxtras.com`: PROXY, REJECT
- `3p-link.com`: PROXY, REJECT
- `3proxy.de`: PROXY, REJECT
- `404.mn`: PROXY, REJECT
- `4040.idv.tw`: PROXY, REJECT
- `466453.com`: PROXY, REJECT
- `4anime.to`: PROXY, REJECT
- `4cdn.org`: PROXY, REJECT
- `4chan.org`: PROXY, REJECT
- `4dq.com`: PROXY, REJECT
- `4dsply.com`: DIRECT, REJECT
- `4everproxy.com`: PROXY, REJECT
- `4irc.com`: PROXY, REJECT
- `4mydomain.com`: PROXY, REJECT
- `4paradigm.com`: DIRECT, REJECT
- `4proxy.de`: PROXY, REJECT
- `4pu.com`: PROXY, REJECT
- `4shared.com`: PROXY, REJECT
- `4thunter.net`: PROXY, REJECT
- `500px.com`: PROXY, REJECT
- `500px.org`: PROXY, REJECT
- `50bang.org`: DIRECT, REJECT
- `51.com`: DIRECT, REJECT
- `51.la`: DIRECT, REJECT
- `51yes.com`: DIRECT, REJECT
- `52pk.com`: DIRECT, REJECT
- `52z.com`: DIRECT, REJECT
- `53kf.com`: DIRECT, REJECT
- `5566ua.com`: DIRECT, REJECT
- `55bet.com`: PROXY, REJECT
- `58.com`: DIRECT, PROXY
- `5dimes.eu`: PROXY, REJECT
- `5lu8.com`: PROXY, REJECT
- `5w.fit`: PROXY, REJECT
- `688.org`: PROXY, REJECT
- `71.am`: DIRECT, REJECT
- `71edge.com`: DIRECT, PROXY
- `7mmtv.tv`: PROXY, REJECT
- `7moor-fs1.com`: DIRECT, REJECT
- `7moor.com`: DIRECT, REJECT
- `7torrents.cc`: PROXY, REJECT
- `7vpn.com`: PROXY, REJECT
- `8686c.com`: DIRECT, PROXY
- `888.com`: PROXY, REJECT
- `888poker.com`: PROXY, REJECT
- `88btbtt.com`: PROXY, REJECT
- `88cdn.com`: DIRECT, REJECT
- `8aa.com`: PROXY, REJECT
- `8kun.top`: PROXY, REJECT
- `991.com`: PROXY, REJECT
- `999d.com`: DIRECT, REJECT
- `9cache.com`: PROXY, REJECT
- `9gag.com`: DIRECT, PROXY, REJECT
- `9ht.com`: DIRECT, PROXY
- `9kb.me`: PROXY, REJECT
- `9xu.com`: DIRECT, REJECT
- `a.magsrv.com`: PROXY, REJECT
- `a.teads.tv`: PROXY, REJECT
- `a1.mzstatic.com`: DIRECT, REJECT
- `a2zapk.com`: PROXY, REJECT
- `aaaa5115.com`: PROXY, REJECT
- `ab.co`: PROXY, REJECT
- `abchina.com`: DIRECT, PROXY
- `abercrombie.com`: DIRECT, PROXY
- `abrdns.com`: PROXY, REJECT
- `accesscam.org`: PROXY, REJECT
- `accountkit.com`: PROXY, REJECT
- `acebook.com`: PROXY, REJECT
- `aceheibao.com`: PROXY, REJECT
- `acevpn.com`: PROXY, REJECT
- `acfun.tv`: DIRECT, PROXY
- `acg.mn`: PROXY, REJECT
- `acg.rip`: DIRECT, PROXY, REJECT
- `acgnx.se`: PROXY, REJECT
- `acgvideo.com`: DIRECT, PROXY
- `acmetoy.com`: PROXY, REJECT
- `activity-zhendingtech.com`: DIRECT, REJECT
- `activpn.com`: PROXY, REJECT
- `ad-maven.com`: PROXY, REJECT
- `ad.12306.cn`: DIRECT, REJECT
- `adash.man.aliyuncs.com`: DIRECT, REJECT
- `adbkwai.com`: DIRECT, REJECT
- `adcdownload.apple.com.akadns.net`: DIRECT, PROXY
- `addthis.com`: DIRECT, REJECT
- `adexchangeprediction.com`: DIRECT, REJECT
- `adf.ly`: DIRECT, REJECT
- `adguard-vpn.com`: PROXY, REJECT
- `adkwai.com`: DIRECT, REJECT
- `adme-net.com`: PROXY, REJECT
- `admin5.com`: DIRECT, REJECT
- `admob-cn.com`: DIRECT, REJECT
- `admob.com`: PROXY, REJECT
- `adnetworkperformance.com`: PROXY, REJECT
- `adobe.com`: DIRECT, PROXY
- `adobedtm.com`: PROXY, REJECT
- `adplxmd.com`: PROXY, REJECT
- `adpost.com`: PROXY, REJECT
- `ads-twitter.com`: PROXY, REJECT
- `ads.exoclick.com`: PROXY, REJECT
- `ads.google.com`: PROXY, REJECT
- `adsense.com`: PROXY, REJECT
- `adsense.google.cn`: PROXY, REJECT
- `adserverplus.com`: PROXY, REJECT
- `adserverpub.com`: PROXY, REJECT
- `adservice.google.com`: DIRECT, REJECT
- `adultfriendfinder.com`: PROXY, REJECT
- `adultproxy.men`: PROXY, REJECT
- `advanced.name`: PROXY, REJECT
- `advertisercommunity.com`: PROXY, REJECT
- `advertising.amazon.co.jp`: PROXY, REJECT
- `adxvip.com`: DIRECT, REJECT
- `aelitis.com`: PROXY, REJECT
- `afd.l.google.com`: PROXY, REJECT
- `affsoft.cc`: PROXY, REJECT
- `agora.io`: DIRECT, PROXY
- `agoralab.co`: DIRECT, REJECT
- `agrantsem.com`: DIRECT, REJECT
- `ahaspeed.com`: PROXY, REJECT
- `ahcdn.com`: PROXY, REJECT
- `aikapool.com`: PROXY, REJECT
- `ainudez.com`: PROXY, REJECT
- `aiosearch.com`: PROXY, REJECT
- `air-matters.com`: DIRECT, PROXY
- `airbrake.io`: PROXY, REJECT

## Publication boundary

This stage does not add sources to the active registry, does not approve domains, and does not alter the three rule sets. Two genuinely independent, verified publishers and all existing deterministic gates remain required.
