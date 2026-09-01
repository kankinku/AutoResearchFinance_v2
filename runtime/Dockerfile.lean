FROM mcr.microsoft.com/dotnet/runtime:8.0-bookworm-slim

# This image is an isolated research worker. It contains no KIS credentials,
# dashboard server, or order capability; the runner also disables networking.
WORKDIR /app
COPY publish/ /app/
USER 65532:65532
ENTRYPOINT ["dotnet", "Quant.dll"]
