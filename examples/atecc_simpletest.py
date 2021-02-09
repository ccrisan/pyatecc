# SPDX-FileCopyrightText: 2021 ladyada for Adafruit Industries
# SPDX-License-Identifier: MIT

import pyatecc


# Initialize a new atecc object
atecc = pyatecc.ATECC(1)

print("ATECC Serial: ", atecc.serial_number)

# Generate a random number with a maximum value of 1024
print("Random Value: ", atecc.random(rnd_max=1024))

# Print out the value from one of the ATECC's counters
# You should see this counter increase on every time the code.py runs.
print("ATECC Counter #1 Value: ", atecc.counter(1, increment_counter=True))

# Initialize the SHA256 calculation engine
atecc.sha_start()

# Append bytes to the SHA digest
print("Appending to the digest...")
atecc.sha_update(b"Nobody inspects")
print("Appending to the digest...")
atecc.sha_update(b" the spammish repetition")

# Return the digest of the data passed to sha_update
message = atecc.sha_digest()
print("SHA Digest: ", message)
