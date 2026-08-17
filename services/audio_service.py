from pydub import AudioSegment


def convert_to_wav(input_path, output_path):
    """Convert an uploaded audio/video file to a mono WAV for Gemini."""
    audio = AudioSegment.from_file(input_path)
    audio = audio.set_channels(1).set_frame_rate(24000)
    audio.export(output_path, format="wav")
