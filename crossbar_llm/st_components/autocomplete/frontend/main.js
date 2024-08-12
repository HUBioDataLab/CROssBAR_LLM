function sendValue(value) {
  Streamlit.setComponentValue(value);
}

function debounce(func, wait) {
  let timeout;
  return function (...args) {
    clearTimeout(timeout);
    timeout = setTimeout(() => func.apply(this, args), wait);
  };
}

function onRender(event) {
  if (!window.rendered) {
    const { label, value, suggestions } = event.detail.args;

    console.log("Suggestions received: ", suggestions);  // Debug log

    const fuse = new Fuse(suggestions, {
      includeScore: true,
      threshold: 0.3,
      shouldSort: true,
      distance: 100,
    });


    const input = document.getElementById("input_box");
    if (value) {
      input.value = value;
    }

    input.addEventListener("input", debounce(function (e) {
      sendValue(e.target.value);
      const lastWord = e.target.value.split(" ").pop(); // Get the last word
      autocomplete(lastWord);
    }, 300));

    function autocomplete(val) {
      let a, b, i;
      closeAllLists();
      if (!val) { return false; }
      a = document.createElement("DIV");
      a.setAttribute("id", "autocomplete-list");
      a.setAttribute("class", "autocomplete-items");
      input.parentNode.appendChild(a);
      const results = fuse.search(val).slice(0, 20);
      console.log("Autocomplete results: ", results);  // Debug log
      for (i = 0; i < results.length; i++) {
        b = document.createElement("DIV");
        b.innerHTML = "<strong>" + results[i].item.substr(0, val.length) + "</strong>";
        b.innerHTML += results[i].item.substr(val.length);
        b.innerHTML += "<input type='hidden' value='" + results[i].item + "'>";
        b.addEventListener("click", function (e) {
          const words = input.value.split(" ");
          words.pop(); // Remove the last word
          words.push(this.getElementsByTagName("input")[0].value);
          input.value = words.join(" ");
          sendValue(input.value);
          closeAllLists();
        });
        a.appendChild(b);
      }
    }

    function closeAllLists(elmnt) {
      const x = document.getElementsByClassName("autocomplete-items");
      for (let i = 0; i < x.length; i++) {
        if (elmnt != x[i] && elmnt != input) {
          x[i].parentNode.removeChild(x[i]);
        }
      }
    }

    document.addEventListener("click", function (e) {
      closeAllLists(e.target);
    });

    window.rendered = true;
  }
}

Streamlit.events.addEventListener(Streamlit.RENDER_EVENT, onRender);
Streamlit.setComponentReady();
Streamlit.setFrameHeight(200);