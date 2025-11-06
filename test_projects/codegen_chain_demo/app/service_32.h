#pragma once
#include <functional>
#include <vector>

class Service32 {
public:
    Service32();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
