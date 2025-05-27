
# airodor-wifi
provide a  api for the airodor wifi module from limot

## install poetry

```bash
curl -sSL https://install.python-poetry.org | python3 - --version $(cat ./.poetry-version)
poetry self add poetry-multiproject-plugin
```


## connect codespace with local network
using the GitHub cli:
```bash
gh net
```

for more details check this https://github.com/github/gh-net#codespaces-network-bridge

## Reverse Engineered API
General address to contact

```http://<ip-address>/msg?Function=<action><group><mode>```

mode is only relevant in case something is "written" (set)

```
action = [R, W, T, S, M] 
where:
  R = READ MODE 
  W = SET MODE 
  T = READ OFF-TIMER 
  S = SET OFF-TIMER 
```
 
```
group = [A, B, D, S, T] 

A = vent group A
B = vent group B
currently: D, S, T are unknown, where S, T might be the filter status
Three messages are therefor unknown:
RS0
RT0
RD68
```

```
mode: 
  ventilation modes:
  
  setting status
    0 = Off 
    1 = min - alternating 
    2 = med - alternating
    3 = med - alternating (do not use, see reading status)
    4 = max - alternating 
    8 = med - permanent one direction
    16 = max - permanent one direction
    32 = med - permanent only to inside
    64 = max - permanent only to inside
    
  reading status
    0 = Off 
    1 = min - alternating 
    2 = med - alternating
    3 = med - alternating (Forced because of invalid input. E.g. hard wire is set to alternat-med and we tried to set alternate-min)
    6 = max - alternating 
    10 = med - permanent one direction
    18 = max - permanent one direction
    34 = med - permanent only to inside
    66 = max - permanent only to inside
    130 = off - with airodor-wifi timer activated
```

right after setting a new mode, the returned mode is the "set" mode value. 
After some seconds the mode switches to the "read" mode values

```
  timer modes: (timers are only usable to turn the ventilation off, not for other modes)
    0 = off 
    1..12 = hours 
```
```
answers: 
  R -> value = R<group><mode> e.g. RA2 for Reading Group A is Mode 2
  W -> success = M<group>OK  e.g. MAOK for setting mode to Group A is OK 
  T -> value = T<group><mode> 
  S -> success = S<group>OK 
```


  

