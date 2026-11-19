#!/usr/bin/env python3
"""Python 3.9+, stdlib only. Sends legacy ZXTouch task 10; receiver decides PASS.

Coordinates are PORTRAIT physical pixels, not CSS pixels or UIKit points.
No acknowledgements are expected from the legacy touch command.
"""
import argparse
import json
import math
import socket
import time


def frame(touches):
    if not 1 <= len(touches) <= 9:
        raise ValueError('one protocol frame contains 1..9 changes')
    parts = ['10', str(len(touches))]
    seen = set()
    for kind, slot, x, y in touches:
        if kind not in (0, 1, 2) or not 0 <= slot <= 19 or slot in seen:
            raise ValueError('invalid phase, slot or duplicate slot')
        seen.add(slot)
        if not all(math.isfinite(v) and 0 <= v <= 9999.9 for v in (x, y)):
            raise ValueError('invalid coordinate')
        parts.append('{}{:02d}{:05d}{:05d}'.format(kind, slot, int(x*10), int(y*10)))
    return (''.join(parts) + '\r\n').encode('ascii')


def run(args):
    # Construct and validate all frames before connecting to a real device.
    slots = [args.slot] if args.mode != 'two' else [args.slot, args.second_slot]
    down = [(1, slot, args.x + i*args.spacing, args.y) for i, slot in enumerate(slots)]
    frame(down)
    end_delta = args.distance if args.mode != 'tap' else 0
    frame([(0, slot, args.x + i*args.spacing + end_delta*(1 if i == 0 else -1), args.y)
           for i, slot in enumerate(slots)])
    rows = []
    with socket.create_connection((args.host, args.port), timeout=5) as sock:
        sock.settimeout(5)
        def send(touches):
            sock.sendall(frame(touches))
            row = {'wall':time.time(), 'monotonic':time.monotonic(), 'sent':touches}
            rows.append(row)
        print('Receiver and ZXTouch indicator must be ready BEFORE countdown.', flush=True)
        if args.mode == 'physical-first':
            print('Hold a physical finger on LEFT now; keep it down through virtual UP.', flush=True)
        elif args.mode == 'virtual-first':
            print('Add physical finger on LEFT after virtual DOWN; move it independently.', flush=True)
        time.sleep(args.countdown)
        positions = [(0, slot, x, y) for _, slot, x, y in down]
        try:
            # If sendall partially fails, finally still attempts UP for every slot.
            send(down)
            print('virtual DOWN', flush=True)
            start = time.monotonic()
            while time.monotonic()-start < args.duration:
                time.sleep(0.1)
                fraction = min(1, (time.monotonic()-start)/args.duration)
                delta = args.distance*fraction if args.mode != 'tap' else 0
                # Keep stationary holds alive for the diagnostic inactivity watchdog.
                positions = [(0, slot, x+delta*(1 if i == 0 else -1), y)
                             for i, (_, slot, x, y) in enumerate(down)]
                send([(2, slot, x, y) for _, slot, x, y in positions])
        finally:
            try:
                send(positions)
                print('virtual UP; verify remaining physical touch still moves, then lift.', flush=True)
            except OSError as error:
                print('UP send failed: {}. Patched server also releases on disconnect/watchdog.'.format(error), flush=True)
            if args.output:
                with open(args.output, 'w', encoding='utf-8') as handle:
                    json.dump({'layer':'TCP send attempts, NOT app receipt', 'args':vars(args), 'rows':rows}, handle, indent=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('host')
    parser.add_argument('--port', type=int, default=6000)
    parser.add_argument('--mode', choices=['tap','swipe','two','physical-first','virtual-first'], default='physical-first')
    parser.add_argument('--slot', type=int, default=7)
    parser.add_argument('--second-slot', type=int, default=9)
    parser.add_argument('--x', type=float, default=800)
    parser.add_argument('--y', type=float, default=1200)
    parser.add_argument('--spacing', type=float, default=200)
    parser.add_argument('--distance', type=float, default=80)
    parser.add_argument('--duration', type=float, default=6)
    parser.add_argument('--countdown', type=float, default=5)
    parser.add_argument('--output')
    args = parser.parse_args()
    if not (math.isfinite(args.duration) and 0.05 <= args.duration <= 60 and
            math.isfinite(args.countdown) and 0 <= args.countdown <= 60):
        parser.error('duration must be 0.05..60, countdown 0..60 seconds')
    if args.mode == 'tap':
        args.duration = 0.1
    run(args)


if __name__ == '__main__':
    main()
