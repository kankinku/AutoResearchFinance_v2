FROM mcr.microsoft.com/dotnet/runtime:8.0-bookworm-slim

WORKDIR /app
COPY publish/ /app/
USER 65532:65532
ENTRYPOINT ["dotnet", "Quant.dll"]
