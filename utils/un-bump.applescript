-- debump-min: mtime := birth time (APFS)
-- No toca la creación, no renombra, no mueve

on run {input, parameters}
	repeat with aFile in input
		set p to POSIX path of (aFile as alias)
		-- Obtener la creación ya formateada para touch: YYYYMMDDhhmm.SS
		set ts to do shell script "/usr/bin/stat -f %SB -t %Y%m%d%H%M.%S " & quoted form of p
		-- Fijar mtime
		do shell script "/usr/bin/touch -mt " & ts & space & quoted form of p
	end repeat
end run