document.addEventListener("DOMContentLoaded", function () {
    const graphScript = document.getElementById("graph-data");
    const graphContainer = document.getElementById("graph");

    if (!graphScript || !graphContainer) {
        return;
    }

    const graphData = JSON.parse(graphScript.textContent);

    const nodes = new vis.DataSet(graphData.nodes || []);
    const edges = new vis.DataSet(graphData.edges || []);

    const options = {
        autoResize: true,
        height: "500px",
        width: "100%",

        physics: {
            enabled: false
        },

        layout: {
            improvedLayout: false
        },

        interaction: {
            hover: true,
            tooltipDelay: 150,
            dragNodes: true,
            dragView: true,
            zoomView: true,
            navigationButtons: false,
            keyboard: false
        },

        nodes: {
            shape: "box",
            margin: 10,
            widthConstraint: {
                minimum: 120,
                maximum: 210
            },
            font: {
                size: 13,
                face: "Arial",
                align: "center"
            },
            borderWidth: 2,
            shadow: false
        },

        groups: {
            main: {
                color: {
                    background: "#93c5fd",
                    border: "#2563eb"
                },
                font: {
                    size: 14,
                    face: "Arial",
                    color: "#111827"
                }
            },

            supplier: {
                color: {
                    background: "#dbeafe",
                    border: "#60a5fa"
                }
            },

            customer: {
                color: {
                    background: "#dcfce7",
                    border: "#22c55e"
                }
            },

            contract: {
                color: {
                    background: "#f8fafc",
                    border: "#94a3b8"
                },
                font: {
                    size: 12,
                    face: "Arial",
                    color: "#334155"
                }
            },

            closed_contract: {
                color: {
                    background: "#fff7ed",
                    border: "#fb923c"
                },
                font: {
                    size: 12,
                    face: "Arial",
                    color: "#9a3412"
                }
            },

            closed: {
                color: {
                    background: "#fee2e2",
                    border: "#ef4444"
                },
                font: {
                    size: 13,
                    face: "Arial",
                    color: "#991b1b"
                }
            }
        },

        edges: {
            smooth: {
                enabled: true,
                type: "continuous"
            },
            color: {
                color: "#94a3b8",
                highlight: "#2563eb",
                hover: "#2563eb"
            },
            arrows: {
                to: {
                    enabled: true,
                    scaleFactor: 0.7
                }
            },
            font: {
                size: 0
            }
        }
    };

    const network = new vis.Network(
        graphContainer,
        {
            nodes: nodes,
            edges: edges
        },
        options
    );

    addGraphControls(graphContainer, network);

    setTimeout(function () {
        network.fit({
            animation: false
        });

        network.moveTo({
            position: {
                x: 0,
                y: 0
            },
            scale: 0.75
        });
    }, 200);
});

function addGraphControls(graphContainer, network) {
    const controls = document.createElement("div");
    controls.className = "graph-controls";

    const zoomInButton = createGraphControlButton("+", "Увеличить масштаб");
    const zoomOutButton = createGraphControlButton("-", "Уменьшить масштаб");
    const resetButton = createGraphControlButton("⤢", "Показать весь граф");

    zoomInButton.addEventListener("click", function () {
        zoomGraph(network, 1.2);
    });

    zoomOutButton.addEventListener("click", function () {
        zoomGraph(network, 1 / 1.2);
    });

    resetButton.addEventListener("click", function () {
        network.fit({
            animation: {
                duration: 180,
                easingFunction: "easeInOutQuad"
            }
        });
    });

    controls.append(zoomInButton, zoomOutButton, resetButton);
    graphContainer.appendChild(controls);
}

function createGraphControlButton(label, title) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "graph-control-button";
    button.textContent = label;
    button.title = title;
    button.setAttribute("aria-label", title);
    return button;
}

function zoomGraph(network, factor) {
    const nextScale = Math.max(0.2, Math.min(2.5, network.getScale() * factor));

    network.moveTo({
        position: network.getViewPosition(),
        scale: nextScale,
        animation: {
            duration: 150,
            easingFunction: "easeInOutQuad"
        }
    });
}
