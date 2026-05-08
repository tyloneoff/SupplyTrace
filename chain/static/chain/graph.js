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