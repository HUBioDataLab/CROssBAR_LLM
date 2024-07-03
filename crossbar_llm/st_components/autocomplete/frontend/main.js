// The `Streamlit` object exists because our html file includes
// `streamlit-component-lib.js`.
// If you get an error about "Streamlit" not being defined, that
// means you're missing that file.

function sendValue(value) {
  Streamlit.setComponentValue(value);
}

/**
 * The component's render function. This will be called immediately after
 * the component is initially loaded, and then again every time the
 * component gets new data from Python.
 */
function onRender(event) {
  // Only run the render code the first time the component is loaded.
  if (!window.rendered) {
    // Grab the label and default value that the user specified
    const { label, value } = event.detail.args;

    // Set the label text to be what the user specified
    const label_el = document.getElementById("label");
    label_el.innerText = label;

    // Set the default value to be what the user specified
    const input = document.getElementById("input_box");
    if (value) {
      input.value = value;
    }

    // On the keyup event, send the new value to Python
    input.onkeyup = (event) => sendValue(event.target.value);

    window.rendered = true;
  }
}

// Render the component whenever python send a "render event"
Streamlit.events.addEventListener(Streamlit.RENDER_EVENT, onRender);
// Tell Streamlit that the component is ready to receive events
Streamlit.setComponentReady();
// Render with the correct height, if this is a fixed-height component
Streamlit.setFrameHeight(100);
