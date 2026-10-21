# USA EV charging data

This folder contains data from the EV Watts public database. 


## Files

| File | Description |
| --- | --- |
| `evwatts.public.session.csv` | Large table of fully anonymized EV charging sessions (plug-in/out times, energy charged, locations) |
| `evwatts.public.vehicles.csv` | Metadata about vehices in the "vehiclesessions" table |
| `evwatts.public.vehiclesessions.csv` | A smaller dataset of EV charging sessions correlated to specific vehicles |

## EV charging datasets (Zenodo)

Download from:

All scripts can be downloaded from [here](https://livewire.energy.gov/ds/evwatts/evwatts.public).

Dataset: *Electric vehicle charging dataset with nearly 14 million charging sessions in the united states.

Note that the vehiclesessions dataset should be sorted by vehicle id before further processing. This can be accomplished with the Unix sort command:
```
LC_ALL=C sort -t ',' -k 2,2 --parallel=4 -T /var/tmp/ -o evwatts.public.vehiclesessions.sorted-by-vehicle.csv evwatts.public.vehiclesessions.csv
```

