document.addEventListener("DOMContentLoaded", function () {
    const graphScript = document.getElementById("graph-data");
    const graphContainer = document.getElementById("graph");

    if (!graphScript || !graphContainer) {
        return;
    }

    const graphData = JSON.parse(graphScript.textContent);

    const isAggregated = graphData.mode === "aggregated";
    const nodes = new vis.DataSet(prepareGraphItems(graphData.nodes || []));
    const edges = new vis.DataSet(prepareGraphItems(graphData.edges || []));

    const options = {
        autoResize: true,
        height: isAggregated ? "560px" : "500px",
        width: "100%",

        physics: {
            enabled: false
        },

        layout: {
            improvedLayout: false,
            randomSeed: 7
        },

        interaction: {
            hover: true,
            hoverConnectedEdges: true,
            selectConnectedEdges: true,
            tooltipDelay: 150,
            dragNodes: true,
            dragView: true,
            zoomView: true,
            navigationButtons: false,
            keyboard: {
                enabled: true,
                bindToWindow: false
            }
        },

        nodes: {
            shape: "box",
            margin: 10,
            widthConstraint: {
                minimum: 120,
                maximum: isAggregated ? 240 : 210
            },
            font: {
                size: 13,
                face: "Arial",
                align: "center"
            },
            borderWidth: 2,
            shadow: false,
            chosen: {
                node: function (values) {
                    values.borderWidth = 3;
                    values.shadow = true;
                }
            }
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
                type: isAggregated ? "cubicBezier" : "continuous",
                forceDirection: isAggregated ? "horizontal" : "none",
                roundness: isAggregated ? 0.35 : 0.5
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
            },
            width: isAggregated ? 2 : 1.6,
            hoverWidth: 2.8,
            selectionWidth: 3,
            scaling: {
                min: 1,
                max: 5
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
    bindGraphHoverState(graphContainer, network);
    bindGraphDetails(graphContainer, network, nodes, edges);

    setTimeout(function () {
        network.fit({
            animation: {
                duration: 220,
                easingFunction: "easeInOutQuad"
            }
        });
    }, 200);
});

function prepareGraphItems(items) {
    return items.map(function (item) {
        return {
            ...item,
            label: createBoundedGraphLabel(item),
            title: createTooltipElement(item.details, item.title)
        };
    });
}

function createBoundedGraphLabel(item) {
    if (!item.label) {
        return item.label;
    }

    const maxLineLength = item.group === "main" ? 21 : 19;
    const maxNameLines = item.group === "contract" || item.group === "closed_contract" ? 2 : 3;
    const lines = String(item.label).split("\n");
    const innLine = lines.find(function (line) {
        return line.trim().toUpperCase().startsWith("ИНН ");
    });
    const nameText = lines.filter(function (line) {
        return line !== innLine;
    }).join(" ");
    const nameLines = wrapGraphLabelText(nameText, maxLineLength, maxNameLines);

    if (innLine) {
        nameLines.push(innLine.trim());
    }

    return nameLines.join("\n");
}

function wrapGraphLabelText(text, maxLineLength, maxLines) {
    const normalized = String(text || "").replace(/\s+/g, " ").trim();

    if (!normalized) {
        return [];
    }

    const words = normalized.split(" ");
    const lines = [];
    let currentLine = "";

    words.forEach(function (word) {
        const chunks = splitLongGraphWord(word, maxLineLength);

        chunks.forEach(function (chunk) {
            const nextLine = currentLine ? `${currentLine} ${chunk}` : chunk;

            if (nextLine.length <= maxLineLength) {
                currentLine = nextLine;
                return;
            }

            if (currentLine) {
                lines.push(currentLine);
            }
            currentLine = chunk;
        });
    });

    if (currentLine) {
        lines.push(currentLine);
    }

    if (lines.length <= maxLines) {
        return lines;
    }

    const trimmed = lines.slice(0, maxLines);
    trimmed[maxLines - 1] = withEllipsis(trimmed[maxLines - 1], maxLineLength);
    return trimmed;
}

function splitLongGraphWord(word, maxLineLength) {
    if (word.length <= maxLineLength) {
        return [word];
    }

    const chunks = [];
    for (let index = 0; index < word.length; index += maxLineLength) {
        chunks.push(word.slice(index, index + maxLineLength));
    }
    return chunks;
}

function withEllipsis(value, maxLineLength) {
    if (value.length <= maxLineLength - 3) {
        return `${value}...`;
    }
    return `${value.slice(0, maxLineLength - 3)}...`;
}

function createTooltipElement(details, fallbackText) {
    const tooltip = document.createElement("div");
    tooltip.className = "graph-tooltip-content";

    if (!details) {
        tooltip.textContent = fallbackText || "";
        return tooltip;
    }

    const heading = document.createElement("strong");
    heading.textContent = details.heading || "Детали";
    tooltip.appendChild(heading);

    (details.items || []).slice(0, 5).forEach(function (item) {
        const row = document.createElement("span");
        row.textContent = `${item.label}: ${item.value}`;
        tooltip.appendChild(row);
    });

    return tooltip;
}

function addGraphControls(graphContainer, network) {
    const controls = document.createElement("div");
    controls.className = "graph-controls";

    const zoomInButton = createGraphControlButton("+", "Увеличить масштаб");
    const zoomOutButton = createGraphControlButton("-", "Уменьшить масштаб");
    const resetButton = createGraphControlButton("Fit", "Показать весь граф");

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

function bindGraphDetails(graphContainer, network, nodes, edges) {
    const panel = document.createElement("aside");
    panel.className = "graph-details-panel";
    graphContainer.insertAdjacentElement("afterend", panel);

    renderGraphDetails(panel, null);

    network.on("select", function (params) {
        if (params.nodes.length) {
            renderGraphDetails(panel, nodes.get(params.nodes[0]), "node");
            return;
        }

        if (params.edges.length) {
            renderGraphDetails(panel, edges.get(params.edges[0]), "edge");
            return;
        }

        renderGraphDetails(panel, null);
    });

    network.on("click", function (params) {
        if (!params.nodes.length && !params.edges.length) {
            renderGraphDetails(panel, null);
        }
    });
}

function renderGraphDetails(panel, item, type) {
    panel.replaceChildren();

    if (!item || !item.details) {
        const title = document.createElement("h3");
        title.textContent = "Детали графа";

        const text = document.createElement("p");
        text.textContent = "Выберите компанию, закупку или стрелку на графе, чтобы увидеть подробную информацию в удобном виде.";

        panel.append(title, text);
        return;
    }

    const badge = document.createElement("span");
    badge.className = "graph-details-badge";
    badge.textContent = getGraphDetailsBadge(item.details.kind, type);

    const title = document.createElement("h3");
    title.textContent = item.details.heading || "Детали";

    const list = document.createElement("dl");
    list.className = "graph-details-list";

    (item.details.items || []).forEach(function (detail) {
        const term = document.createElement("dt");
        term.textContent = detail.label;

        const description = document.createElement("dd");
        description.textContent = detail.value;

        list.append(term, description);
    });

    panel.append(badge, title, list);
}

function getGraphDetailsBadge(kind, type) {
    if (kind === "aggregate") {
        return "Агрегированная связь";
    }
    if (kind === "edge" || type === "edge") {
        return "Связь";
    }
    if (kind === "contract") {
        return "Закупка / контракт";
    }
    if (kind === "closed") {
        return "Закрытая закупка";
    }
    if (kind === "company") {
        return "Центральная компания";
    }
    return "Участник";
}

function bindGraphHoverState(graphContainer, network) {
    network.on("hoverNode", function () {
        graphContainer.classList.add("graph-is-hovering");
    });

    network.on("hoverEdge", function () {
        graphContainer.classList.add("graph-is-hovering");
    });

    network.on("blurNode", function () {
        graphContainer.classList.remove("graph-is-hovering");
    });

    network.on("blurEdge", function () {
        graphContainer.classList.remove("graph-is-hovering");
    });

    network.on("dragStart", function () {
        graphContainer.classList.add("graph-is-dragging");
    });

    network.on("dragEnd", function () {
        graphContainer.classList.remove("graph-is-dragging");
    });
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
