import pyaudio

p = pyaudio.PyAudio()
print("\n--- AVAILABLE AUDIO DEVICES ---")

for i in range(p.get_device_count()):
    info = p.get_device_info_by_index(i)
    print(f"Device ID {i}: {info['name']} (Inputs: {info['maxInputChannels']}, Outputs: {info['maxOutputChannels']})")

p.terminate()