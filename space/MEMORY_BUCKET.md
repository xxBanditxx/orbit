# Orbit Memory Bucket

Orbit can persist `data/beliefs.json` in a private Hugging Face bucket.

Required Space configuration:

- Secret: `HF_TOKEN`
- Variable: `ORBIT_BUCKET_ID=xxbanditxx/orbit-memory`
- Optional variable: `ORBIT_BUCKET_PATH=beliefs.json`

The launcher restores the remote snapshot before importing the app. After every recorded evidence item, Orbit writes the updated snapshot back to the bucket.

Safety behavior:

- If the bucket is empty, Orbit seeds a first snapshot and uploads it.
- If the bucket cannot be read, Orbit continues locally.
- If startup could not read the bucket, remote writes remain blocked for that process to prevent accidental overwrite.
