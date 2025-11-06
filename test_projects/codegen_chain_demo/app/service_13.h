#pragma once
#include <functional>
#include <vector>

class Service13 {
public:
    Service13();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
