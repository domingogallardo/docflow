-- "bump" para Shortcuts/Finder: coloca archivos arriba ajustando solo mtime
-- Comportamiento:
--  - Base: 2100-01-01 00:00:00
--  - Por carpeta: busca el mayor mtime futuro existente y continúa desde ahí
--  - +1s por archivo manteniendo el orden de entrada
--  - No renombra, no mueve, no modifica contenido

on run {input, parameters}
    -- Versión rápida: usar 'date' y 'touch' vía shell, sin iterar con Finder
    -- Base dinámica: ahora + 100 años; +1s por archivo para mantener orden
    set counter to 0
    repeat with aFile in input
        set counter to counter + 1
        set p to POSIX path of (aFile as alias)
        -- Construir timestamp: YYYYMMDDhhmm.SS en hora local
        set ts to do shell script "/bin/date -v+100y -v+" & counter & "S +%Y%m%d%H%M.%S"
        do shell script "/usr/bin/touch -mt " & ts & space & quoted form of p
    end repeat
end run


