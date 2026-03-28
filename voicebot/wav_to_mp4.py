from pydub import AudioSegment

# Convert WAV to MP4
audio = AudioSegment.from_wav(filename)
mp4_filename = filename.replace(".wav", ".mp4")
audio.export(mp4_filename, format="mp4")
print(f"Saved assistant audio to {mp4_filename}")