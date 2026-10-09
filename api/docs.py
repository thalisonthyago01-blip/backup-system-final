from fastapi.responses import HTMLResponse


def custom_docs():
    html = """
    <!DOCTYPE html>
    <html lang="pt-BR">

    <head>
        <meta charset="UTF-8">

        <meta
            name="viewport"
            content="width=device-width, initial-scale=1.0"
        >

        <title>Backup System API</title>

        <link
            rel="stylesheet"
            href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css"
        >

        <style>
            body {
                margin: 0;
                padding: 0;
                font-family: Arial, sans-serif;
                background: #1f2428;
            }
        
            .backup-panel {
                margin: 16px;
                padding: 20px;
                border: 1px solid #3d444b;
                border-radius: 8px;
                background: #252a2e;
                color: #e6e6e6;
            }
        
            .backup-panel h2 {
                margin-top: 0;
                color: #ffffff;
            }
        
            .backup-panel p {
                color: #c9c9c9;
            }
        
            .folder-input {
                display: none;
            }
        
            .folder-button {
                display: inline-block;
                padding: 10px 16px;
                border: 0;
                border-radius: 5px;
                background: #4990e2;
                color: #ffffff;
                cursor: pointer;
                font-size: 14px;
            }
        
            .folder-button:hover {
                background: #357abd;
            }
        
            .backup-button {
                display: inline-block;
                margin-left: 8px;
                padding: 10px 16px;
                border: 0;
                border-radius: 5px;
                background: #49a078;
                color: #ffffff;
                cursor: pointer;
                font-size: 14px;
            }
        
            .backup-button:hover {
                background: #3b8665;
            }
        
            .backup-button:disabled {
                background: #555;
                color: #aaa;
                cursor: not-allowed;
            }
        
            .selected-files {
                margin-top: 15px;
                padding: 10px;
                background: #1b1f22;
                border: 1px solid #3d444b;
                border-radius: 5px;
                max-height: 250px;
                overflow-y: auto;
                color: #e6e6e6;
            }
        
            .selected-files div {
                padding: 4px 0;
                font-family: monospace;
                font-size: 13px;
                color: #dcdcdc;
            }
        
            .status {
                margin-top: 15px;
                padding: 10px;
                border-radius: 5px;
                display: none;
                white-space: pre-wrap;
                font-family: monospace;
            }
        
            .status.success {
                display: block;
                background: #183a2b;
                border: 1px solid #2e7655;
                color: #b9f6d0;
            }
        
            .status.error {
                display: block;
                background: #401f23;
                border: 1px solid #8b3a43;
                color: #ffb8be;
            }
        </style>
    </head>

    <body>

        <div class="backup-panel">

            <h2>Teste de Backup por Pasta</h2>

            <p>
                Selecione uma pasta inteira para criar um backup
                preservando sua estrutura de diretórios.
            </p>

            <input
                id="folderInput"
                class="folder-input"
                type="file"
                webkitdirectory
                directory
                multiple
            >

            <label
                for="folderInput"
                class="folder-button"
            >
                Selecionar pasta
            </label>

            <button
                id="backupButton"
                class="backup-button"
                disabled
            >
                Criar backup
            </button>

            <div
                id="selectedFiles"
                class="selected-files"
            >
                Nenhuma pasta selecionada.
            </div>

            <div
                id="status"
                class="status"
            ></div>

        </div>


        <div id="swagger-ui"></div>


        <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>

        <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-standalone-preset.js"></script>


        <script>

            const folderInput =
                document.getElementById("folderInput");

            const backupButton =
                document.getElementById("backupButton");

            const selectedFiles =
                document.getElementById("selectedFiles");

            const status =
                document.getElementById("status");


            let arquivosSelecionados = [];


            folderInput.addEventListener(
                "change",
                function() {

                    arquivosSelecionados =
                        Array.from(folderInput.files);


                    selectedFiles.innerHTML = "";


                    if (arquivosSelecionados.length === 0) {

                        selectedFiles.textContent =
                            "Nenhuma pasta selecionada.";

                        backupButton.disabled = true;

                        return;
                    }


                    const titulo =
                        document.createElement("div");

                    titulo.innerHTML =
                        "<strong>" +
                        arquivosSelecionados.length +
                        " arquivo(s) selecionado(s)</strong>";

                    selectedFiles.appendChild(titulo);


                    arquivosSelecionados.forEach(
                        function(file) {

                            const item =
                                document.createElement("div");


                            const caminho =
                                file.webkitRelativePath ||
                                file.name;


                            item.textContent =
                                caminho;


                            selectedFiles.appendChild(item);
                        }
                    );


                    backupButton.disabled = false;

                    status.className = "status";

                    status.textContent = "";
                }
            );


            backupButton.addEventListener(
                "click",
                async function() {

                    if (
                        arquivosSelecionados.length === 0
                    ) {
                        return;
                    }


                    backupButton.disabled = true;

                    status.className = "status";

                    status.textContent =
                        "Enviando arquivos...";


                    const formData =
                        new FormData();


                    arquivosSelecionados.forEach(
                        function(file) {

                            const caminho =
                                file.webkitRelativePath ||
                                file.name;


                            formData.append(
                                "files",
                                file,
                                caminho
                            );
                        }
                    );


                    try {

                        const response =
                            await fetch(
                                "/backup",
                                {
                                    method: "POST",
                                    body: formData
                                }
                            );


                        const resultado =
                            await response.json();


                        if (!response.ok) {

                            throw new Error(
                                JSON.stringify(
                                    resultado,
                                    null,
                                    2
                                )
                            );
                        }


                        status.className =
                            "status success";


                        status.textContent =
                            "Backup criado com sucesso!\\n\\n" +
                            JSON.stringify(
                                resultado,
                                null,
                                2
                            );


                    } catch (error) {

                        status.className =
                            "status error";


                        status.textContent =
                            "Erro ao criar backup:\\n\\n" +
                            error.message;

                    } finally {

                        backupButton.disabled = false;

                    }

                }
            );


            window.onload = function() {

                window.ui =
                    SwaggerUIBundle({

                        url: "/openapi.json",

                        dom_id: "#swagger-ui",

                        deepLinking: true,

                        presets: [
                            SwaggerUIBundle.presets.apis,
                            SwaggerUIStandalonePreset
                        ],

                        plugins: [
                            SwaggerUIBundle.plugins.DownloadUrl
                        ],

                        layout: "StandaloneLayout"

                    });

            };

        </script>

    </body>

    </html>
    """

    return HTMLResponse(content=html)