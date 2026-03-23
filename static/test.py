pp = 1325
pulseinflation = 1.2
def getpulses(pp, multiplier = 1):
    pulses = pp
    pulses *= multiplier
    pulses **= pulseinflation
    return pulses

print(getpulses(1, 1), "only 1")
print(getpulses(2, 1), "only 2")
print(getpulses(5, 1), "only 5")
print(getpulses(24, 1), "only 24")
print(getpulses(512, 1), "512 amount")
print(getpulses(pp, 1), "my pulse")
print(getpulses(31812, 1), "someones pulse")
print(1 / pulseinflation)