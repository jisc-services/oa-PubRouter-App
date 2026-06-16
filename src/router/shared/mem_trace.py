import tracemalloc
from octopus.lib.dates import now_str

# list to store memory snapshots
snaps = []

def start(num_frames=1):
    tracemalloc.start(num_frames)

def stop():
    tracemalloc.stop()

def snapshot(clear_all=False):
    global snaps
    if clear_all:
        snaps = []
    try:
        snaps.append(tracemalloc.take_snapshot())
    except Exception:
        pass
    return len(snaps)


def pre_string(desc):
    return "\n\n***MMM*** " + now_str('%Y-%m-%d %H:%M:%S') + " * " + desc


def print_last_snapshot_stats(desc="", stat_type='filename', num_stats=10):
    """
    :param desc: String - Description
    :param stat_type: String - One of 'filename', 'lineno', 'traceback'
    :param num_stats: Int - Top x statistics
    """
    global snaps
    try:
        stats = snaps[-1].statistics(stat_type)
        print(f"{pre_string(desc)} Top {num_stats} stats grouped by {stat_type} ***")
        for s in stats[:num_stats]:
            print(s)
    except Exception:
        pass


def compare_snapshots(desc="", first_ix=0, last_ix=-1, stat_type='lineno', num_stats=10):
    global snaps

    try:
        first = snaps[first_ix]
        last = snaps[last_ix]
        stats = last.compare_to(first, stat_type)
        print(f"{pre_string(desc)}  Comparing snapshot {first_ix} with snapshot {last_ix} - top {num_stats} stats ***")
        for s in stats[:num_stats]:
            print(s)
    except Exception:
        pass


def compare_all_snapshots(desc="", num_stats=10):
    global snaps
    for ix in range(1, len(snaps)):
        compare_snapshots(desc, 0, ix, num_stats=num_stats)


def print_last_snapshot_trace(desc=""):
    global snaps

    try:
        # pick the last saved snapshot, filter noise
        snapshot = snaps[-1].filter_traces((
            tracemalloc.Filter(False, "<frozen importlib._bootstrap>"),
            tracemalloc.Filter(False, "<frozen importlib._bootstrap_external>"),
            tracemalloc.Filter(False, "<unknown>"),
        ))
        largest = snapshot.statistics("traceback")[0]

        print(f"{pre_string(desc)} Trace for largest memory block - ({largest.count} blocks, {largest.size / 1024} Kb) ***")
        for l in largest.traceback.format():
            print(l)
    except Exception:
        pass
