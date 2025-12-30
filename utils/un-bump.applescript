-- debump-min: mtime := birth time (APFS)
-- Does not touch creation time, does not rename, does not move

on run {input, parameters}
	repeat with aFile in input
		set p to POSIX path of (aFile as alias)
		-- Get creation time formatted for touch: YYYYMMDDhhmm.SS
		set ts to do shell script "/usr/bin/stat -f %SB -t %Y%m%d%H%M.%S " & quoted form of p
		-- Set mtime
		do shell script "/usr/bin/touch -mt " & ts & space & quoted form of p
	end repeat
end run
