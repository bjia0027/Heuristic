#pragma once
#include <functional>
#include <vector>

class Service10 {
public:
    Service10();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
