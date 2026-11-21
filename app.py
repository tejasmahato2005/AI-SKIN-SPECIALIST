import gradio as gr
from main import iface, CSS

if __name__ == "__main__":
    iface.launch(css=CSS, theme=gr.themes.Base())

